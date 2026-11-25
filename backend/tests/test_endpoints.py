import io
from unittest.mock import patch

from fastapi.testclient import TestClient


def _get_test_client() -> TestClient:
    with (
        patch("os.path.exists", return_value=True),
        patch("app.translator.NLLBTranslator._init_models", return_value=None),
    ):
        import app.main as main_mod

        def fake_translate_stream(text, source_lang, target_lang, device="cpu"):
            yield f"[{source_lang}->{target_lang}] {text} "

        main_mod.translator.translate_stream = fake_translate_stream
        main_mod.translator._split_into_sentences = lambda t: [
            s.strip() for s in t.split(".") if s.strip()
        ]
        return TestClient(main_mod.app)


def test_health_endpoint():
    client = _get_test_client()
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "status" in data
    assert "device" in data
    assert "queue_size" in data


def test_translate_stream_empty_text():
    client = _get_test_client()
    resp = client.post("/translate/stream", json={"text": "   "})
    assert resp.status_code == 400


def test_translate_stream_success():
    client = _get_test_client()
    resp = client.post(
        "/translate/stream",
        json={"text": "Dobar dan.", "source_lang": "bos_Latn", "target_lang": "ukr_Cyrl"},
    )
    assert resp.status_code == 200
    assert "[bos_Latn->ukr_Cyrl] Dobar dan." in resp.text
    assert "[DONE]" in resp.text


def test_translate_file_txt():
    client = _get_test_client()
    file_bytes = io.BytesIO(b"Dobar dan.")
    resp = client.post(
        "/translate/file?debug=false",
        files={"upload_file": ("test.txt", file_bytes, "text/plain")},
    )
    assert resp.status_code == 200
    assert "[bos_Latn->ukr_Cyrl] Dobar dan" in resp.text
