"""Minimal in-memory per-key rate limiter (SEC-2 interim).

Fixed-window counting: at most `limit` calls per `window_seconds` per key.
Deliberately simple and in-process only — this is a stopgap against
casual abuse of a cost-spending endpoint, not a production rate limiter.
Under multiple gunicorn worker processes each worker holds its own
counters, so the *effective* limit is roughly `limit * worker_count`.
That gap is accepted for this interim mitigation; the durable fix is real
per-user auth + quotas at the Next.js migration's API boundary (see
NextJSWebDesign.md), not a distributed limiter for a Flask POC.
"""
import time
import threading
from collections import defaultdict, deque


class RateLimiter:
    def __init__(self, limit: int, window_seconds: float):
        self.limit = limit
        self.window_seconds = window_seconds
        self._hits = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str, now: float = None) -> bool:
        """Return True and record a hit if `key` is under the limit for the
        current window; return False without recording a hit otherwise."""
        now = time.time() if now is None else now
        with self._lock:
            hits = self._hits[key]
            cutoff = now - self.window_seconds
            while hits and hits[0] <= cutoff:
                hits.popleft()
            if len(hits) >= self.limit:
                return False
            hits.append(now)
            return True
