
from app.rate_limiter import RateLimitStore, _sign, _verify


def test_rate_limit_store_allows_burst():
    store = RateLimitStore(requests_per_minute=60, burst=3)
    for _ in range(3):
        allowed, _ = store.is_allowed("test-key")
        assert allowed is True
    # 4th should be denied
    allowed, retry = store.is_allowed("test-key")
    assert allowed is False
    assert retry > 0


def test_rate_limit_store_replenishes():
    store = RateLimitStore(requests_per_minute=600, burst=1)
    allowed, _ = store.is_allowed("key")
    assert allowed is True
    allowed, _ = store.is_allowed("key")
    assert allowed is False
    # Simulate time passing
    store._buckets["key"]._last_refill -= 1.0
    allowed, _ = store.is_allowed("key")
    assert allowed is True


def test_cookie_sign_and_verify():
    secret = "test-secret"
    value = "abc123"
    signed = _sign(value, secret)
    assert "." in signed
    assert _verify(signed, secret) == value
    assert _verify(signed + "x", secret) is None
    assert _verify("tampered.sig", secret) is None


def test_rate_limit_middleware_returns_429():
    """Integration test: middleware returns 429 after burst is exhausted."""
    from app.config import Settings
    from app.main import create_app
    from fastapi.testclient import TestClient
    from tests.fakes import FakeBackend

    settings = Settings(rate_limit_rpm=60, rate_limit_burst=2, cookie_secret="test")
    app = create_app(settings=settings, backend=FakeBackend())
    client = TestClient(app)

    # First 2 requests should succeed
    for _ in range(2):
        resp = client.post(
            "/translate/stream",
            json={"text": "test", "source_lang": "bos_Latn", "target_lang": "ukr_Cyrl"},
        )
        assert resp.status_code == 200

    # 3rd request should be rate limited
    resp = client.post(
        "/translate/stream",
        json={"text": "test", "source_lang": "bos_Latn", "target_lang": "ukr_Cyrl"},
    )
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers


def test_health_endpoint_bypasses_rate_limit():
    """Health endpoint should not be rate limited."""
    from app.config import Settings
    from app.main import create_app
    from fastapi.testclient import TestClient
    from tests.fakes import FakeBackend

    settings = Settings(rate_limit_rpm=60, rate_limit_burst=1, cookie_secret="test")
    app = create_app(settings=settings, backend=FakeBackend())
    client = TestClient(app)

    # Exhaust the burst on a translate call
    client.post(
        "/translate/stream",
        json={"text": "test", "source_lang": "bos_Latn", "target_lang": "ukr_Cyrl"},
    )

    # Health should still work
    resp = client.get("/health")
    assert resp.status_code == 200


def _limited_client(burst: int):
    from app.config import Settings
    from app.main import create_app
    from fastapi.testclient import TestClient
    from tests.fakes import FakeBackend

    settings = Settings(
        rate_limit_rpm=1,
        rate_limit_burst=burst,
        cookie_secret="test",
        cors_origins="https://front.example",
    )
    return TestClient(create_app(settings=settings, backend=FakeBackend()))


def _translate(client, headers=None):
    client.cookies.clear()
    return client.post("/translate/stream", json={"text": "test"}, headers=headers)


def test_spoofed_forwarded_for_does_not_bypass_ip_limit():
    """Only the rightmost entry is appended by the trusted proxy."""
    client = _limited_client(burst=1)
    first = _translate(client, {"X-Forwarded-For": "10.0.0.1, 203.0.113.9"})
    second = _translate(client, {"X-Forwarded-For": "10.0.0.2, 203.0.113.9"})
    assert (first.status_code, second.status_code) == (200, 429)


def test_clients_behind_proxy_are_limited_separately():
    client = _limited_client(burst=1)
    first = _translate(client, {"X-Forwarded-For": "203.0.113.1"})
    second = _translate(client, {"X-Forwarded-For": "203.0.113.2"})
    assert (first.status_code, second.status_code) == (200, 200)


def test_rate_limited_response_keeps_cors_headers():
    client = _limited_client(burst=1)
    origin = {"Origin": "https://front.example"}
    _translate(client, origin)
    resp = _translate(client, origin)
    assert resp.status_code == 429
    assert resp.headers.get("access-control-allow-origin") == "https://front.example"


def test_cors_preflight_does_not_consume_rate_limit():
    client = _limited_client(burst=1)
    preflight = {
        "Origin": "https://front.example",
        "Access-Control-Request-Method": "POST",
    }
    for _ in range(3):
        assert client.options("/translate/stream", headers=preflight).status_code == 200
    assert _translate(client).status_code == 200


def test_reading_job_status_is_not_rate_limited():
    client = _limited_client(burst=1)
    codes = {client.get("/translate/file/status?job_id=x").status_code for _ in range(10)}
    assert codes == {404}
