
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
    from tests.test_endpoints import MockBackend

    settings = Settings(rate_limit_rpm=60, rate_limit_burst=2, cookie_secret="test")
    app = create_app(settings=settings, backend=MockBackend())
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
    from tests.test_endpoints import MockBackend

    settings = Settings(rate_limit_rpm=60, rate_limit_burst=1, cookie_secret="test")
    app = create_app(settings=settings, backend=MockBackend())
    client = TestClient(app)

    # Exhaust the burst on a translate call
    client.post(
        "/translate/stream",
        json={"text": "test", "source_lang": "bos_Latn", "target_lang": "ukr_Cyrl"},
    )

    # Health should still work
    resp = client.get("/health")
    assert resp.status_code == 200
