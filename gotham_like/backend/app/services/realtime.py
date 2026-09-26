"""WebSocket hub: live alerts, investigation updates, collaborative changes, query progress.

Messages are published from sync code (request handlers, workers) with `publish()`.
When Redis is configured, messages fan out through Redis pub/sub so multiple API
workers share one bus; otherwise they are delivered in-process.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from collections import defaultdict
from typing import Any

from starlette.websockets import WebSocket

from app.config import get_settings
from app.models import utcnow

log = logging.getLogger("tessera.ws")
REDIS_CHANNEL = "tessera:events"


class Hub:
    def __init__(self) -> None:
        self.loop: asyncio.AbstractEventLoop | None = None
        self.clients: dict[WebSocket, dict[str, Any]] = {}
        self.topics: dict[str, set[WebSocket]] = defaultdict(set)
        self._redis = None
        self._redis_thread: threading.Thread | None = None
        self.published: list[dict[str, Any]] = []  # recent messages (diagnostics/tests)

    # ------------------------------------------------------------------ lifecycle
    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop
        url = get_settings().redis_url
        if not url or self._redis_thread:
            return
        try:
            import redis

            self._redis = redis.Redis.from_url(url, socket_connect_timeout=0.5)
            self._redis.ping()
            pubsub = self._redis.pubsub(ignore_subscribe_messages=True)
            pubsub.subscribe(REDIS_CHANNEL)

            def pump() -> None:
                for msg in pubsub.listen():
                    try:
                        data = json.loads(msg["data"])
                    except (TypeError, ValueError):
                        continue
                    if self.loop:
                        asyncio.run_coroutine_threadsafe(self._deliver(data), self.loop)

            self._redis_thread = threading.Thread(target=pump, name="ws-redis", daemon=True)
            self._redis_thread.start()
        except Exception:  # noqa: BLE001
            self._redis = None
            log.warning("redis pub/sub unavailable; websocket fan-out is in-process only")

    # ------------------------------------------------------------------ clients
    async def connect(self, ws: WebSocket, user: dict[str, Any]) -> None:
        self.clients[ws] = user
        self.topics["alerts"].add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self.clients.pop(ws, None)
        for subs in self.topics.values():
            subs.discard(ws)

    def subscribe(self, ws: WebSocket, topic: str) -> None:
        self.topics[topic].add(ws)

    def unsubscribe(self, ws: WebSocket, topic: str) -> None:
        self.topics[topic].discard(ws)

    # ------------------------------------------------------------------ publish
    def publish(self, topic: str, event: str, payload: dict[str, Any]) -> None:
        msg = {"topic": topic, "event": event, "payload": payload, "ts": utcnow().isoformat()}
        self.published.append(msg)
        del self.published[:-200]
        if self._redis is not None:
            try:
                self._redis.publish(REDIS_CHANNEL, json.dumps(msg, default=str))
                return
            except Exception:  # noqa: BLE001
                pass
        if self.loop and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(self._deliver(msg), self.loop)

    async def _deliver(self, msg: dict[str, Any]) -> None:
        dead = []
        for ws in list(self.topics.get(msg["topic"], ())):
            try:
                await ws.send_text(json.dumps(msg, default=str))
            except Exception:  # noqa: BLE001
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


hub = Hub()
