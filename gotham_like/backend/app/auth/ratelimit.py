"""Fixed-window rate limiting (Redis when available, in-process fallback)."""

from __future__ import annotations

import logging
import threading
import time

from app.config import get_settings

log = logging.getLogger("tessera.ratelimit")


class RateLimiter:
    def __init__(self) -> None:
        self._redis = None
        self._local: dict[str, tuple[int, int]] = {}
        self._lock = threading.Lock()
        url = get_settings().redis_url
        if url:
            try:
                import redis

                client = redis.Redis.from_url(url, socket_connect_timeout=0.5, socket_timeout=0.5)
                client.ping()
                self._redis = client
            except Exception:  # noqa: BLE001 - fall back silently, logged once
                log.warning("redis unavailable; using in-process rate limiting")

    def hit(self, key: str, limit: int, window_s: int = 60) -> tuple[bool, int]:
        """Returns (allowed, remaining)."""
        window = int(time.time() // window_s)
        full = f"rl:{key}:{window}"
        if self._redis is not None:
            try:
                pipe = self._redis.pipeline()
                pipe.incr(full)
                pipe.expire(full, window_s + 1)
                count = int(pipe.execute()[0])
                return count <= limit, max(limit - count, 0)
            except Exception:  # noqa: BLE001
                pass
        with self._lock:
            w, count = self._local.get(key, (window, 0))
            if w != window:
                w, count = window, 0
            count += 1
            self._local[key] = (w, count)
            if len(self._local) > 50_000:
                self._local = {k: v for k, v in self._local.items() if v[0] == window}
            return count <= limit, max(limit - count, 0)

    def reset(self) -> None:
        with self._lock:
            self._local.clear()
        if self._redis is not None:
            try:
                for k in self._redis.scan_iter("rl:*"):
                    self._redis.delete(k)
            except Exception:  # noqa: BLE001
                pass


_limiter: RateLimiter | None = None


def get_limiter() -> RateLimiter:
    global _limiter
    if _limiter is None:
        _limiter = RateLimiter()
    return _limiter
