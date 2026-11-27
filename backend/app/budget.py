"""Daily allowance per visitor, so one person cannot use up the shared GPU quota.

Counted in characters, because GPU time grows with the length of the text.
Held in memory: a restart resets it.
"""

import time

DAY_SECONDS = 86_400


class DailyBudget:
    def __init__(self, limit: int, window_seconds: int = DAY_SECONDS, max_entries: int = 10_000):
        self.limit = limit
        self.window_seconds = window_seconds
        self.max_entries = max_entries
        # key -> [time of first use, amount used], oldest first
        self._used: dict[str, list[float]] = {}

    def try_spend(self, key: str, amount: int) -> bool:
        """Count `amount` against the key, unless that would exceed its limit."""
        now = time.monotonic()
        entry = self._used.get(key)
        if entry and now - entry[0] >= self.window_seconds:
            del self._used[key]
            entry = None
        if (entry[1] if entry else 0) + amount > self.limit:
            return False
        if entry is None:
            if len(self._used) >= self.max_entries:
                del self._used[next(iter(self._used))]
            entry = self._used[key] = [now, 0]
        entry[1] += amount
        return True

    def refund(self, key: str, amount: int) -> None:
        """Give back what a failed translation was charged."""
        if entry := self._used.get(key):
            entry[1] = max(0, entry[1] - amount)
