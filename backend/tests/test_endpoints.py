import io
import json
from typing import AsyncGenerator
from unittest.mock import MagicMock, patch

import pytest
from app.backends import RemoteBackend, TranslatorBackend
from app.config import Settings
from app.main import create_app
from fastapi.testclient import TestClient


class MockBackend(TranslatorBackend):
    def __init__(self, fail: bool = False):
        self.fail = fail

    async def translate_stream(
        self, text: str, source_lang: str, target_lang: str
    ) -> AsyncGenerator[str, None]:
        if self.fail:
            raise RuntimeError("secret internal stack trace")
        yield f"[{source_lang}->{target_lang}] {text} "


def _client(fail: bool = False, max_upload_bytes: int = 1024 * 1024) -> TestClient:
    settings = Settings(max_upload_bytes=max_upload_bytes)
    app = create_app(settings=settings, backend=MockBackend(fail=fail))
    return TestClient(app)


def test_health_endpoint():
    client = _client()
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert data["device"] == "remote"
    assert "queue_size" in data


def test_translate_stream_empty_text():
    client = _client()
    resp = client.post("/translate/stream", json={"text": "   "})
    assert resp.status_code == 400


def test_translate_stream_success():
    client = _client()
    resp = client.post(
        "/translate/stream",
        json={"text": "Dobar dan.", "source_lang": "bos_Latn", "target_lang": "ukr_Cyrl"},
    )
    assert resp.status_code == 200
    assert "[bos_Latn->ukr_Cyrl] Dobar dan." in resp.text
    assert "[DONE]" in resp.text


def test_translate_stream_error_is_generic():
    client = _client(fail=True)
    resp = client.post(
        "/translate/stream",
        json={"text": "Dobar dan.", "source_lang": "bos_Latn", "target_lang": "ukr_Cyrl"},
    )
    assert resp.status_code == 200
    assert "Translation failed" in resp.text
    assert "secret internal stack trace" not in resp.text
    assert "[Помилка" not in resp.text


def test_translate_file_defaults_to_direct_file():
    client = _client()
    file_bytes = io.BytesIO(b"Dobar dan.")
    resp = client.post(
        "/translate/file",
        files={"upload_file": ("test.txt", file_bytes, "text/plain")},
    )
    assert resp.status_code == 200
    assert "text/plain" in resp.headers["content-type"]
    assert "[bos_Latn->ukr_Cyrl] Dobar dan." in resp.text


def test_translate_file_rejects_unsupported_extension():
    client = _client()
    resp = client.post(
        "/translate/file",
        files={"upload_file": ("malware.exe", io.BytesIO(b"MZ"), "application/octet-stream")},
    )
    assert resp.status_code == 415


def test_translate_file_rejects_oversized_upload():
    client = _client(max_upload_bytes=10)
    resp = client.post(
        "/translate/file",
        files={"upload_file": ("big.txt", io.BytesIO(b"x" * 100), "text/plain")},
    )
    assert resp.status_code == 413


def test_translate_file_stream_and_fetch_result():
    client = _client()
    resp = client.post(
        "/translate/file/stream",
        files={"upload_file": ("hello.txt", io.BytesIO(b"Dobar dan."), "text/plain")},
    )
    assert resp.status_code == 200
    job_id = None
    for line in resp.text.splitlines():
        if line.startswith("data:") and "job_id" in line:
            payload = json.loads(line.split("data:", 1)[1].strip())
            job_id = payload.get("job_id")
    assert job_id is not None

    res = client.get(f"/translate/file/result?job_id={job_id}")
    assert res.status_code == 200
    assert "[bos_Latn->ukr_Cyrl] Dobar dan." in res.text


def test_cors_no_wildcard_with_credentials():
    client = _client()
    resp = client.options(
        "/health",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert resp.headers.get("access-control-allow-credentials") != "true"


@pytest.mark.asyncio
async def test_remote_backend_requires_url():
    with pytest.raises(ValueError):
        RemoteBackend("")


@pytest.mark.asyncio
async def test_remote_backend_streams_chunks_and_sends_auth_header():
    backend = RemoteBackend("https://example.hf.space/", api_token="hf_secret")
    assert backend.base_url == "https://example.hf.space"
    assert backend.headers["Authorization"] == "Bearer hf_secret"

    fake_resp = MagicMock()
    fake_resp.raise_for_status = MagicMock()
    fake_resp.iter_lines.return_value = [
        "event: message",
        "data: Привіт ",
        "",
        "event: message",
        "data: світе!",
        "",
        "event: end",
        "data: [DONE]",
    ]

    fake_stream_ctx = MagicMock()
    fake_stream_ctx.__enter__.return_value = fake_resp
    fake_stream_ctx.__exit__.return_value = False

    fake_client = MagicMock()
    fake_client.stream.return_value = fake_stream_ctx
    fake_client.__enter__.return_value = fake_client
    fake_client.__exit__.return_value = False

    with patch("app.backends.httpx.Client", return_value=fake_client):
        chunks = [
            c async for c in backend.translate_stream("Zdravo.", "bos_Latn", "ukr_Cyrl")
        ]

    assert chunks == ["Привіт ", "світе!"]


@pytest.mark.asyncio
async def test_remote_backend_health_reports_waking_up_when_unreachable():
    backend = RemoteBackend("https://example.hf.space")
    with patch("app.backends.httpx.Client", side_effect=RuntimeError("timeout")):
        health = await backend.check_health()
    assert health is not None
    assert health["status"] == "Waking up"
    assert health["reachable"] is False


def test_settings_parses_comma_separated_cors_origins():
    cfg = Settings(cors_origins="https://app.example.com, http://localhost:5173")
    assert cfg.cors_origins == ["https://app.example.com", "http://localhost:5173"]
