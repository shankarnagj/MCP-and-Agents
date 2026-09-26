"""Read-through cache for expensive, deterministic reads (graph windows, analytics, search).

Keys include a global data version, bumped on every write that changes the graph
(ingestion, entity resolution, verification), so stale results are never served.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from typing import Any

from app.config import get_settings

_VERSION_KEY = "tessera:data_version"


class Cache:
    def __init__(self, max_items: int = 512) -> None:
        self._local: OrderedDict[str, tuple[float, str]] = OrderedDict()
        self._lock = threading.Lock()
        self._version = 0
        self.max_items = max_items
        self._redis = None
        self.hits = 0
        self.misses = 0
        url = get_settings().redis_url
        if url:
            try:
                import redis

                r = redis.Redis.from_url(url, socket_connect_timeout=0.5, socket_timeout=0.5)
                r.ping()
                self._redis = r
            except Exception:  # noqa: BLE001
                self._redis = None

    def data_version(self) -> int:
        if self._redis is not None:
            try:
                return int(self._redis.get(_VERSION_KEY) or 0)
            except Exception:  # noqa: BLE001
                pass
        return self._version

    def bump(self) -> None:
        self._version += 1
        if self._redis is not None:
            try:
                self._redis.incr(_VERSION_KEY)
            except Exception:  # noqa: BLE001
                pass
        with self._lock:
            self._local.clear()

    def key(self, namespace: str, role: str, payload: Any) -> str:
        blob = json.dumps(payload, sort_keys=True, default=str)
        return f"tessera:c:{namespace}:{self.data_version()}:{role}:{hashlib.sha256(blob.encode()).hexdigest()[:24]}"

    def get_or_set(self, key: str, ttl: int, fn: Callable[[], Any]) -> Any:
        now = time.time()
        with self._lock:
            hit = self._local.get(key)
            if hit and hit[0] > now:
                self._local.move_to_end(key)
                self.hits += 1
                return json.loads(hit[1])
        if self._redis is not None:
            try:
                raw = self._redis.get(key)
                if raw is not None:
                    self.hits += 1
                    return json.loads(raw)
            except Exception:  # noqa: BLE001
                pass
        self.misses += 1
        value = fn()
        blob = json.dumps(value, default=str)
        with self._lock:
            self._local[key] = (now + ttl, blob)
            while len(self._local) > self.max_items:
                self._local.popitem(last=False)
        if self._redis is not None:
            try:
                self._redis.setex(key, ttl, blob)
            except Exception:  # noqa: BLE001
                pass
        return json.loads(blob)


_cache: Cache | None = None


def get_cache() -> Cache:
    global _cache
    if _cache is None:
        _cache = Cache()
    return _cache
