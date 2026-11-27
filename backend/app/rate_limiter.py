"""Simple in-process rate limiter with per-IP and signed-cookie session counters.

Enough for a single-dyno demo. A shared store (Redis) is needed for several instances.
"""

import hashlib
import hmac
import logging
import time
import uuid
from typing import Any

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Token-bucket implementation
# ---------------------------------------------------------------------------


class _TokenBucket:
    """Simple in-memory token-bucket rate limiter."""

    __slots__ = ("rate", "capacity", "_tokens", "_last_refill")

    def __init__(self, rate: float, capacity: int) -> None:
        self.rate = rate  # tokens per second
        self.capacity = capacity
        self._tokens = float(capacity)
        self._last_refill = time.monotonic()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
        self._last_refill = now

    def consume(self, tokens: int = 1) -> bool:
        self._refill()
        if self._tokens >= tokens:
            self._tokens -= tokens
            return True
        return False

    @property
    def retry_after(self) -> float:
        self._refill()
        if self._tokens >= 1:
            return 0.0
        return (1.0 - self._tokens) / self.rate


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


class RateLimitStore:
    """Per-key token-bucket store with automatic eviction of stale entries."""

    def __init__(
        self,
        requests_per_minute: int = 20,
        burst: int = 5,
        max_entries: int = 10_000,
    ) -> None:
        self.rate = requests_per_minute / 60.0
        self.burst = burst
        self.max_entries = max_entries
        self._buckets: dict[str, _TokenBucket] = {}
        self._last_cleanup = time.monotonic()

    def _maybe_cleanup(self) -> None:
        now = time.monotonic()
        if now - self._last_cleanup < 60:
            return
        self._last_cleanup = now
        # Evict buckets that haven't been used for 5 minutes
        stale_keys = [
            k
            for k, b in self._buckets.items()
            if now - b._last_refill > 300
        ]
        for k in stale_keys:
            del self._buckets[k]

    def is_allowed(self, key: str) -> tuple[bool, float]:
        """Return (allowed, retry_after_seconds) for the given key."""
        self._maybe_cleanup()
        bucket = self._buckets.get(key)
        if bucket is None:
            if len(self._buckets) >= self.max_entries:
                # Evict oldest bucket
                oldest = min(self._buckets, key=lambda k: self._buckets[k]._last_refill)
                del self._buckets[oldest]
            bucket = _TokenBucket(self.rate, self.burst)
            self._buckets[key] = bucket
        allowed = bucket.consume()
        return allowed, bucket.retry_after


# ---------------------------------------------------------------------------
# Cookie signing helpers
# ---------------------------------------------------------------------------

_COOKIE_NAME = "bs_session"


def _sign(value: str, secret: str) -> str:
    sig = hmac.new(secret.encode(), value.encode(), hashlib.sha256).hexdigest()[:16]
    return f"{value}.{sig}"


def _verify(signed: str, secret: str) -> str | None:
    parts = signed.rsplit(".", 1)
    if len(parts) != 2:
        return None
    value, sig = parts
    expected = hmac.new(secret.encode(), value.encode(), hashlib.sha256).hexdigest()[:16]
    if hmac.compare_digest(sig, expected):
        return value
    return None


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------


def _get_client_ip(request: Request) -> str:
    """Extract client IP, respecting X-Forwarded-For behind a proxy.

    Only the rightmost entry is used: the trusted proxy (the Heroku router)
    appends it, while everything to its left is supplied by the client.
    """
    forwarded = ",".join(request.headers.getlist("x-forwarded-for"))
    if forwarded:
        return forwarded.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-IP + per-session rate limiting middleware.

    Both keys must pass for a request to be allowed.  The session is
    tracked via a signed anonymous cookie so that clearing cookies
    resets the session but does not bypass the IP limit.
    """

    def __init__(
        self,
        app: Any,
        requests_per_minute: int = 20,
        burst: int = 5,
        *,
        cookie_secret: str,
    ) -> None:
        super().__init__(app)
        self.ip_store = RateLimitStore(requests_per_minute, burst)
        self.session_store = RateLimitStore(requests_per_minute, burst)
        self.cookie_secret = cookie_secret

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Only POST requests cost GPU time; health checks and job polling are free
        if request.method != "POST":
            return await call_next(request)

        client_ip = _get_client_ip(request)

        # Read or create session from signed cookie
        session_id: str | None = None
        raw_cookie = request.cookies.get(_COOKIE_NAME)
        if raw_cookie:
            session_id = _verify(raw_cookie, self.cookie_secret)
        if not session_id:
            session_id = uuid.uuid4().hex
        request.state.visitor = session_id  # used to recognise repeated requests

        ip_allowed, ip_retry = self.ip_store.is_allowed(f"ip:{client_ip}")
        sess_allowed, sess_retry = self.session_store.is_allowed(f"sess:{session_id}")

        if not ip_allowed or not sess_allowed:
            retry_after = max(ip_retry, sess_retry)
            logger.warning(
                "Rate limited: ip=%s session=%s retry_after=%.1f",
                client_ip,
                session_id[:8],
                retry_after,
            )
            response: Response = JSONResponse(
                {"detail": "Забагато запитів. Спробуйте пізніше."},
                status_code=429,
                headers={"Retry-After": str(int(retry_after) + 1)},
            )
        else:
            response = await call_next(request)

        # Always set/refresh the session cookie
        response.set_cookie(
            _COOKIE_NAME,
            _sign(session_id, self.cookie_secret),
            httponly=True,
            samesite="lax",
            max_age=86400,
        )
        return response
