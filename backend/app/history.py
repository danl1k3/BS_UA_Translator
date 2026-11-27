"""Remember each visitor's recent text translations, so a repeat costs no GPU time.

Keys include the visitor, so nobody learns what someone else has translated.
Held in memory: lost on restart.
"""

import hashlib
import time
from collections.abc import Iterator
from contextlib import contextmanager


def content_key(visitor: str, direction: str, content: bytes) -> str:
    """Identify one visitor's request without keeping its content."""
    digest = hashlib.sha256(content).hexdigest()
    return f"{visitor}:{direction}:{digest}"


class TranslationHistory:
    def __init__(self, ttl_seconds: int = 3600, max_entries: int = 200):
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self._results: dict[str, tuple[float, str]] = {}  # oldest first
        self._running: set[str] = set()

    def result(self, key: str) -> str | None:
        stored = self._results.get(key)
        if stored is None or time.monotonic() - stored[0] > self.ttl_seconds:
            return None
        return stored[1]

    def is_running(self, key: str) -> bool:
        return key in self._running

    @contextmanager
    def running(self, key: str) -> Iterator[None]:
        """Mark a translation as in progress until it ends in any way."""
        self._running.add(key)
        try:
            yield
        finally:
            self._running.discard(key)

    def save(self, key: str, result: str) -> None:
        self._results.pop(key, None)
        self._results[key] = (time.monotonic(), result)
        while len(self._results) > self.max_entries:
            del self._results[next(iter(self._results))]
