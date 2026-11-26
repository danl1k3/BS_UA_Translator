"""GradioBackend against response shapes captured from Gradio 6.32.0."""

import json

import httpx
import pytest
from app.backends import GradioBackend, QuotaExceededError, TranslationError
from app.config import Settings
from app.main import create_backend

URL = "https://owner-space.hf.space"


def _sse(event: str, data: object) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


class FakeSpace:
    def __init__(self, result: str = "", config_status: int = 200):
        self.result = result
        self.config_status = config_status
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if path == "/config":
            return httpx.Response(self.config_status, json={})
        if path == "/gradio_api/call/translate":
            return httpx.Response(200, json={"event_id": "abc"})
        if path == "/gradio_api/call/translate/abc":
            return httpx.Response(200, text=self.result)
        return httpx.Response(404)


def _backend(space, token: str = "hf_secret") -> GradioBackend:
    return GradioBackend(URL + "/", api_token=token, transport=httpx.MockTransport(space))


async def _translate(backend, text="Prva.\nDruga.", src="bos_Latn", tgt="ukr_Cyrl"):
    return await backend.translate(text, src, tgt)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "src,tgt,direction",
    [("bos_Latn", "ukr_Cyrl", "bs-ua"), ("ukr_Cyrl", "bos_Latn", "ua-bs")],
)
async def test_sends_whole_text_with_direction_and_token(src, tgt, direction):
    space = FakeSpace(_sse("heartbeat", None) + _sse("complete", ["Перша.\nДруга."]))
    result = await _translate(_backend(space), src=src, tgt=tgt)
    assert result == "Перша.\nДруга."
    assert json.loads(space.requests[0].content) == {"data": ["Prva.\nDruga.", direction]}
    assert [r.headers["authorization"] for r in space.requests] == ["Bearer hf_secret"] * 2


@pytest.mark.asyncio
async def test_unsupported_language_pair_makes_no_request():
    space = FakeSpace()
    with pytest.raises(TranslationError):
        await _translate(_backend(space), src="eng_Latn")
    assert space.requests == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"error": "You have exceeded your GPU quota (60s requested vs. 0s left)."},
        {"error": "No GPU time left.", "title": "ZeroGPU quota exceeded"},
    ],
)
async def test_quota_error_is_reported_as_quota(payload):
    with pytest.raises(QuotaExceededError):
        await _translate(_backend(FakeSpace(_sse("error", payload))))


@pytest.mark.asyncio
@pytest.mark.parametrize("result", [_sse("error", {"error": None}), ""])
async def test_failed_or_truncated_response_raises(result):
    with pytest.raises(RuntimeError):
        await _translate(_backend(FakeSpace(result)))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "code,status,reachable",
    [(200, "Normal", True), (401, "Unavailable", False), (503, "Waking up", False)],
)
async def test_health_uses_config_only(code, status, reachable):
    space = FakeSpace(config_status=code)
    health = await _backend(space).check_health()
    assert (health["status"], health["reachable"]) == (status, reachable)
    assert [r.url.path for r in space.requests] == ["/config"]


@pytest.mark.asyncio
async def test_health_is_cached():
    space = FakeSpace()
    backend = _backend(space)
    await backend.check_health()
    await backend.check_health()
    assert len(space.requests) == 1


def test_gateway_builds_the_gradio_backend():
    cfg = Settings(_env_file=None, remote_inference_url=URL)
    assert isinstance(create_backend(cfg), GradioBackend)
