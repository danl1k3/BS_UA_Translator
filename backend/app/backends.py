import json
import logging
import time
from abc import ABC, abstractmethod

import httpx

logger = logging.getLogger(__name__)

# (source, target) -> direction key understood by the Space
LANGUAGE_PAIRS = {
    ("bos_Latn", "ukr_Cyrl"): "bs-ua",
    ("ukr_Cyrl", "bos_Latn"): "ua-bs",
}


class TranslationError(RuntimeError):
    """Inference failure. `public_message` is safe to show to the user."""

    public_message = "Translation failed"


class QuotaExceededError(TranslationError):
    """The ZeroGPU quota of the account that owns the token is used up."""

    public_message = "The daily GPU limit is used up. Try again later."


class TranslatorBackend(ABC):
    """Interface to the inference service."""

    @abstractmethod
    async def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        """Translate text, returning one output line for every input line."""

    @abstractmethod
    async def check_health(self) -> dict[str, object]:
        """Return `status` and `reachable` of the inference service."""

    async def get_quota(self) -> dict[str, object] | None:
        """Return the remaining GPU quota, or None if the backend cannot tell."""
        return None


class GradioBackend(TranslatorBackend):
    """Client for the `/translate` endpoint of a Gradio (ZeroGPU) Space.

    With a token, GPU time is charged to the token owner's quota.
    """

    API_PATH = "/gradio_api/call/translate"
    HEALTH_TTL_SECONDS = 30.0
    QUOTA_URL = "https://huggingface.co/api/spaces/zero-gpu/quota"
    QUOTA_TTL_SECONDS = 15.0

    def __init__(
        self,
        base_url: str,
        timeout: float = 120.0,
        api_token: str = "",
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        if not base_url:
            raise ValueError("REMOTE_INFERENCE_URL must be configured")
        self.base_url = base_url.rstrip("/")
        self.timeout = httpx.Timeout(timeout, connect=15.0)
        self.headers = {"Authorization": f"Bearer {api_token}"} if api_token else {}
        self.transport = transport
        self._health: tuple[float, dict[str, object]] | None = None
        self._quota: tuple[float, dict[str, object] | None] | None = None

    def _client(self, timeout: httpx.Timeout) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.base_url,
            headers=self.headers,
            timeout=timeout,
            transport=self.transport,
        )

    async def check_health(self) -> dict[str, object]:
        """Probe `/config`, which needs no GPU. Cached to limit traffic."""
        now = time.monotonic()
        if self._health and now - self._health[0] < self.HEALTH_TTL_SECONDS:
            return self._health[1]
        status = "Waking up"
        try:
            async with self._client(httpx.Timeout(3.0)) as client:
                code = (await client.get("/config")).status_code
            if code == 200:
                status = "Normal"
            elif code in (401, 403, 404):
                status = "Unavailable"
        except httpx.HTTPError as exc:
            logger.warning("Space health check failed: %s", exc)
        health: dict[str, object] = {"status": status, "reachable": status == "Normal"}
        self._health = (now, health)
        return health

    async def get_quota(self) -> dict[str, object] | None:
        """Quota of the token owner. Cached, so visitors cannot flood Hugging Face."""
        if not self.headers:
            return None
        now = time.monotonic()
        if self._quota and now - self._quota[0] < self.QUOTA_TTL_SECONDS:
            return self._quota[1]
        quota: dict[str, object] | None = None
        try:
            async with self._client(httpx.Timeout(3.0)) as client:
                response = await client.get(self.QUOTA_URL)
            response.raise_for_status()
            data = response.json()
            quota = {
                "remaining_seconds": max(0, int(data["current"])),
                "total_seconds": int(data["base"]),
                "resets_at": data.get("resetsAt"),
            }
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            logger.warning("Could not read the GPU quota: %s", exc)
        self._quota = (now, quota)
        return quota

    async def translate(self, text: str, source_lang: str, target_lang: str) -> str:
        direction = LANGUAGE_PAIRS.get((source_lang, target_lang))
        if direction is None:
            raise TranslationError(f"Unsupported pair: {source_lang} -> {target_lang}")
        try:
            return await self._call_space(text, direction)
        finally:
            self._quota = None  # the call may have used GPU time

    async def _call_space(self, text: str, direction: str) -> str:
        async with self._client(self.timeout) as client:
            submitted = await client.post(self.API_PATH, json={"data": [text, direction]})
            submitted.raise_for_status()
            event_id = submitted.json()["event_id"]

            async with client.stream("GET", f"{self.API_PATH}/{event_id}") as resp:
                resp.raise_for_status()
                event = ""
                async for line in resp.aiter_lines():
                    if line.startswith("event:"):
                        event = line.split(":", 1)[1].strip()
                    elif line.startswith("data:") and event in ("complete", "error"):
                        payload = json.loads(line.split(":", 1)[1])
                        if event == "error":
                            raise self._to_error(payload)
                        return payload[0]

        raise TranslationError("Space closed the stream without a result")

    @staticmethod
    def _to_error(payload: object) -> TranslationError:
        details = payload if isinstance(payload, dict) else {}
        message = f"{details.get('title') or ''}: {details.get('error') or ''}"
        error_type = QuotaExceededError if "quota" in message.lower() else TranslationError
        return error_type(f"Space error: {message}")
