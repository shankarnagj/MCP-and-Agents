"""Structured logging, request IDs, metrics and error tracking."""

from __future__ import annotations

import contextvars
import json
import logging
import sys
import time
import traceback
import uuid
from collections import deque
from datetime import UTC, datetime

from prometheus_client import CollectorRegistry, Counter, Histogram, generate_latest
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")
user_var: contextvars.ContextVar[str] = contextvars.ContextVar("user", default="-")

REGISTRY = CollectorRegistry(auto_describe=True)
HTTP_REQUESTS = Counter(
    "tessera_http_requests_total", "HTTP requests", ["method", "route", "status"], registry=REGISTRY
)
HTTP_LATENCY = Histogram(
    "tessera_http_request_seconds",
    "HTTP request latency",
    ["method", "route"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
    registry=REGISTRY,
)
DB_QUERY_SECONDS = Histogram(
    "tessera_db_query_seconds",
    "Database statement latency",
    ["operation"],
    buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1, 5),
    registry=REGISTRY,
)
ERRORS = Counter("tessera_errors_total", "Unhandled errors", ["route"], registry=REGISTRY)
GRAPH_OPS = Counter("tessera_graph_operations_total", "Graph operations", ["operation"], registry=REGISTRY)
ALERTS_RAISED = Counter("tessera_alerts_total", "Alerts raised", ["rule"], registry=REGISTRY)

SLOW_QUERY_LOGGER = logging.getLogger("tessera.db")

# In-process ring buffer of recent errors (lightweight error tracking; a real
# deployment would forward these to Sentry/OTel via the same hook).
RECENT_ERRORS: deque[dict] = deque(maxlen=200)


class JsonFormatter(logging.Formatter):
    RESERVED = set(vars(logging.makeLogRecord({})).keys()) | {"message", "asctime"}

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": request_id_var.get(),
            "user": user_var.get(),
        }
        for key, value in record.__dict__.items():
            if key not in self.RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO", as_json: bool = True) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter() if as_json else logging.Formatter("%(levelname)s %(name)s %(message)s"))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assigns a request id, measures latency, records metrics, tracks errors."""

    async def dispatch(self, request: Request, call_next):  # noqa: ANN001
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex
        # Only accept sane, client-supplied ids
        if len(rid) > 64 or not all(c.isalnum() or c in "-_" for c in rid):
            rid = uuid.uuid4().hex
        token = request_id_var.set(rid)
        start = time.perf_counter()
        route = request.url.path
        status = 500
        try:
            response: Response = await call_next(request)
            status = response.status_code
            route_obj = request.scope.get("route")
            route = getattr(route_obj, "path", route)
            response.headers["x-request-id"] = rid
            response.headers["x-response-time-ms"] = f"{(time.perf_counter() - start) * 1000:.1f}"
            return response
        except Exception as exc:
            ERRORS.labels(route=route).inc()
            RECENT_ERRORS.append(
                {
                    "ts": datetime.now(UTC).isoformat(),
                    "request_id": rid,
                    "route": route,
                    "error": repr(exc),
                    "trace": traceback.format_exc(limit=8),
                }
            )
            logging.getLogger("tessera.http").exception("unhandled_error")
            raise
        finally:
            elapsed = time.perf_counter() - start
            HTTP_REQUESTS.labels(method=request.method, route=route, status=str(status)).inc()
            HTTP_LATENCY.labels(method=request.method, route=route).observe(elapsed)
            logging.getLogger("tessera.http").info(
                "request",
                extra={"method": request.method, "path": request.url.path, "status": status, "elapsed_ms": round(elapsed * 1000, 1)},
            )
            request_id_var.reset(token)


def metrics_payload() -> bytes:
    return generate_latest(REGISTRY)
