import pytest
from app.config import Settings
from tests.fakes import FakeBackend, QuotaExceededError, make_client


def _translate(client, **body):
    return client.post("/translate/stream", json={"text": "Dobar dan.", **body})


def test_translate_returns_message_and_end_events():
    resp = _translate(make_client(), text="Jedan.\nDva.")
    assert "event: message\r\ndata: JEDAN.\r\ndata: DVA." in resp.text
    assert "data: [DONE]" in resp.text


def test_translate_splits_long_sentences():
    backend = FakeBackend()
    _translate(make_client(backend), text="riječ " * 300)
    assert max(map(len, backend.calls[0].split("\n"))) <= 220


@pytest.mark.parametrize(
    "body,status",
    [({"text": "  "}, 400), ({"text": "x" * 2001}, 422), ({"source_lang": "eng_Latn"}, 400)],
)
def test_translate_rejects_bad_requests(body, status):
    assert _translate(make_client(), **body).status_code == status


@pytest.mark.parametrize(
    "error,event,message",
    [
        (RuntimeError("secret internal stack trace"), "error", "Translation failed"),
        (QuotaExceededError("secret details"), "limit", QuotaExceededError.public_message),
    ],
)
def test_translate_errors_are_safe(error, event, message):
    resp = _translate(make_client(FakeBackend(error)))
    assert f"event: {event}\r\ndata: {message}" in resp.text
    assert "secret" not in resp.text


def test_health_exposes_no_system_metrics():
    data = make_client().get("/health").json()
    assert data == {
        "status": "Normal",
        "queue_size": 0,
        "inference": {"status": "Normal", "reachable": True},
    }


def test_cors_has_no_credentials():
    resp = make_client().options(
        "/health",
        headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"},
    )
    assert resp.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert resp.headers.get("access-control-allow-credentials") != "true"


@pytest.mark.parametrize("secret", ["", "change-me-in-production"])
def test_missing_or_default_cookie_secret_is_replaced(secret):
    first = Settings(_env_file=None, cookie_secret=secret)
    second = Settings(_env_file=None, cookie_secret=secret)
    assert len(first.cookie_secret) >= 32
    assert first.cookie_secret != second.cookie_secret


def test_configured_cookie_secret_is_kept():
    assert Settings(_env_file=None, cookie_secret="mine").cookie_secret == "mine"


def test_settings_parses_comma_separated_cors_origins():
    cfg = Settings(_env_file=None, cors_origins="https://a.example, http://localhost:5173")
    assert cfg.cors_origins == ["https://a.example", "http://localhost:5173"]


def test_huge_text_request_is_refused_before_parsing():
    resp = _translate(make_client(max_upload_bytes=10), text="x" * 100_000)
    assert resp.status_code == 413


def _site(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<title>site</title>")
    (tmp_path / "assets" / "app.js").write_text("console.log(1)")
    return make_client(static_dir=str(tmp_path))


def test_serves_the_built_frontend_next_to_the_api(tmp_path):
    client = _site(tmp_path)
    assert "<title>site</title>" in client.get("/").text
    assert client.get("/assets/app.js").text == "console.log(1)"
    assert client.get("/health").json()["status"] == "Normal"
    assert "[DONE]" in _translate(client).text


def test_static_files_do_not_reach_outside_their_folder(tmp_path):
    (tmp_path / "secret.txt").write_text("secret")
    site = tmp_path / "site"
    site.mkdir()
    client = _site(site)
    assert client.get("/%2e%2e/secret.txt").status_code == 404


def test_api_works_without_a_built_frontend(tmp_path):
    client = make_client(static_dir=str(tmp_path / "missing"))
    assert client.get("/").status_code == 404
    assert client.get("/health").status_code == 200


@pytest.mark.parametrize(
    "path", ["/health", "/translate/file/status?job_id=x", "/translate/file/result?job_id=x"]
)
def test_api_responses_are_never_cached(path):
    assert make_client().get(path).headers["cache-control"] == "no-store"


def test_frontend_files_stay_cacheable(tmp_path):
    assert "no-store" not in _site(tmp_path).get("/").headers.get("cache-control", "")
