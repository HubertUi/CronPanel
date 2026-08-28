"""Sliding window rate limiter.

Stateful per key (IP + username for login). The limiter instance is
process-global; tests must reset it between runs. Thread-safe via Lock
since FastAPI runs synchronous dependencies in the default thread pool.

Clock injection (`clock`) allows deterministic tests; default is
`time.monotonic`.
"""

import threading
import time
from collections import defaultdict, deque

from app.core.config import settings


class SlidingWindowRateLimiter:
    def __init__(
        self,
        max_events: int,
        window_seconds: float,
        clock=None,
    ) -> None:
        self.max_events = max_events
        self.window_seconds = window_seconds
        self.clock = clock or time.monotonic
        self._store: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _purge(self, key: str, now: float) -> None:
        timestamps = self._store[key]
        cutoff = now - self.window_seconds
        while timestamps and timestamps[0] < cutoff:
            timestamps.popleft()
        if not timestamps:
            self._store.pop(key, None)

    def register_failure(self, key: str) -> None:
        with self._lock:
            self._store[key].append(self.clock())

    def is_blocked(self, key: str) -> bool:
        with self._lock:
            now = self.clock()
            self._purge(key, now)
            return len(self._store[key]) >= self.max_events

    def seconds_until_unblocked(self, key: str) -> int:
        """Seconds until the oldest failure expires from the window."""
        with self._lock:
            now = self.clock()
            self._purge(key, now)
            if not self._store[key]:
                return 0
            oldest = self._store[key][0]
            remaining = oldest + self.window_seconds - now
            return max(0, int(remaining) + 1)

    def reset_key(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)

    def reset_all(self) -> None:
        with self._lock:
            self._store.clear()


def login_rate_key(ip: str | None, username: str) -> str:
    return f"{ip or 'unknown'}:{username.strip().lower()}"


login_rate_limiter = SlidingWindowRateLimiter(
    settings.LOGIN_RATE_LIMIT,
    settings.LOGIN_RATE_WINDOW_SECONDS,
)
