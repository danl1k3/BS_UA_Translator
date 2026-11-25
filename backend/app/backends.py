import asyncio
import logging
import threading
from abc import ABC, abstractmethod
from typing import AsyncGenerator

import httpx

from .sentence_splitter import split_sentences

logger = logging.getLogger(__name__)


class TranslatorBackend(ABC):
    """Abstract interface for translation inference backends."""

    def split_into_sentences(self, text: str) -> list[str]:
        """Split text into sentences for chunking."""
        return split_sentences(text)

    async def check_health(self) -> dict[str, object] | None:
        """Check inference service health."""
        return None

    @abstractmethod
    async def translate_stream(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
    ) -> AsyncGenerator[str, None]:
        """Stream translated text chunks asynchronously."""
        yield ""  # pragma: no cover


class RemoteBackend(TranslatorBackend):
    """HTTP SSE client backend calling HF Spaces inference off the event loop."""

    def __init__(
        self,
        base_url: str,
        timeout: float = 120.0,
        api_token: str = "",
    ):
        if not base_url:
            raise ValueError("REMOTE_INFERENCE_URL must be configured")
        self.base_url = base_url.rstrip("/")
        self.timeout = httpx.Timeout(timeout, connect=15.0)
        self.headers: dict[str, str] = {}
        if api_token:
            self.headers["Authorization"] = f"Bearer {api_token}"

    def _health_sync(self) -> dict[str, object]:
        url = f"{self.base_url}/health"
        with httpx.Client(timeout=httpx.Timeout(3.0), headers=self.headers) as client:
            resp = client.get(url)
            resp.raise_for_status()
            return resp.json()

    async def check_health(self) -> dict[str, object] | None:
        try:
            return await asyncio.to_thread(self._health_sync)
        except Exception as e:
            logger.warning("Remote inference health check failed: %s", e)
            return {"status": "Waking up", "device": "remote", "reachable": False}

    def _stream_worker(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
        loop: asyncio.AbstractEventLoop,
        queue: asyncio.Queue[object],
        stop_event: threading.Event,
        sentinel: object,
    ) -> None:
        """Stream SSE chunks from HF Spaces in a worker thread."""
        url = f"{self.base_url}/translate/stream"
        payload = {
            "text": text,
            "source_lang": source_lang,
            "target_lang": target_lang,
        }
        try:
            with httpx.Client(timeout=self.timeout, headers=self.headers) as client:
                with client.stream("POST", url, json=payload) as resp:
                    resp.raise_for_status()
                    current_event = "message"
                    for raw_line in resp.iter_lines():
                        if stop_event.is_set():
                            break
                        line = raw_line.rstrip("\r\n")
                        if not line.strip():
                            continue
                        if line.startswith("event:"):
                            current_event = line.split(":", 1)[1].strip()
                        elif line.startswith("data:"):
                            data = line.split(":", 1)[1].lstrip()
                            if current_event == "error":
                                raise RuntimeError(f"Remote inference error: {data}")
                            if data == "[DONE]":
                                break
                            loop.call_soon_threadsafe(queue.put_nowait, data)
        except Exception as exc:
            loop.call_soon_threadsafe(queue.put_nowait, exc)
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, sentinel)

    async def translate_stream(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
    ) -> AsyncGenerator[str, None]:
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[object] = asyncio.Queue()
        stop_event = threading.Event()
        sentinel = object()

        worker = threading.Thread(
            target=self._stream_worker,
            args=(text, source_lang, target_lang, loop, queue, stop_event, sentinel),
            daemon=True,
        )
        worker.start()

        try:
            while True:
                item = await queue.get()
                if item is sentinel:
                    break
                if isinstance(item, Exception):
                    raise item
                yield str(item)
        finally:
            stop_event.set()
