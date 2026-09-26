"""FastAPI application factory."""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from sqlalchemy import text
from starlette.middleware.base import BaseHTTPMiddleware

from app.api import auth, entities, governance, graph, spatiotemporal, workspace
from app.auth.deps import require
from app.auth.ratelimit import get_limiter
from app.auth.rbac import P_AUDIT
from app.config import get_settings
from app.db import SessionLocal
from app.observability import RECENT_ERRORS, RequestContextMiddleware, configure_logging, metrics_payload
from app.services.cache import get_cache
from app.services.realtime import hub

log = logging.getLogger("tessera.app")

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
    "Permissions-Policy": "geolocation=(), camera=(), microphone=()",
}
MAX_BODY_BYTES = 12 * 1024 * 1024


class SecurityMiddleware(BaseHTTPMiddleware):
    """Rate limiting, request size limits and security headers."""

    async def dispatch(self, request: Request, call_next):  # noqa: ANN001
        path = request.url.path
        if path.startswith("/api/"):
            length = request.headers.get("content-length")
            if length and length.isdigit() and int(length) > MAX_BODY_BYTES:
                return JSONResponse({"detail": "request body too large"}, status_code=413)
            # NUL characters are never valid in this API (and PostgreSQL text rejects them)
            raw_target = request.scope.get("raw_path", b"") + b"?" + request.scope.get("query_string", b"")
            if b"%00" in raw_target or b"\x00" in raw_target:
                return JSONResponse({"detail": "NUL characters are not allowed"}, status_code=422)
            if request.method in ("POST", "PUT", "PATCH") and "json" in request.headers.get("content-type", ""):
                body = await request.body()
                if b"\\u0000" in body or b"\x00" in body:
                    return JSONResponse({"detail": "NUL characters are not allowed"}, status_code=422)
            ip = request.client.host if request.client else "unknown"
            ok, remaining = get_limiter().hit(f"api:{ip}", get_settings().rate_limit_per_minute)
            if not ok:
                return JSONResponse({"detail": "rate limit exceeded"}, status_code=429, headers={"Retry-After": "60"})
        response = await call_next(request)
        for k, v in SECURITY_HEADERS.items():
            if k == "Content-Security-Policy" and path.startswith("/docs"):
                continue  # Swagger UI needs its own assets
            response.headers.setdefault(k, v)
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ANN201
    hub.start(asyncio.get_running_loop())
    yield


def create_app() -> FastAPI:
    s = get_settings()
    configure_logging(s.log_level, s.log_json)
    app = FastAPI(
        title=s.app_name,
        version=s.version,
        description=(
            "Local-first investigative intelligence & decision-support platform. Outputs are decision support: "
            "system inferences and analytical signals are never presented as established facts."
        ),
        lifespan=lifespan,
    )
    app.add_middleware(SecurityMiddleware)
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(CORSMiddleware, allow_origins=s.cors_origins, allow_credentials=False, allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
                       allow_headers=["Authorization", "Content-Type", "X-Request-ID"], expose_headers=["X-Request-ID", "Content-Disposition"])

    for r in (auth.router, auth.users_router, entities.router, graph.router, spatiotemporal.router, workspace.router, governance.router):
        app.include_router(r)

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [{"loc": e.get("loc"), "msg": e.get("msg"), "type": e.get("type")} for e in exc.errors()]
        return JSONResponse({"detail": errors}, status_code=422)

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception) -> JSONResponse:
        # never leak stack traces or SQL to clients
        return JSONResponse({"detail": "internal error", "request_id": request.headers.get("x-request-id")}, status_code=500)

    @app.get("/health", tags=["system"])
    def health() -> dict:
        return {"status": "ok", "version": s.version}

    @app.get("/ready", tags=["system"])
    def ready() -> Response:
        checks = {}
        try:
            with SessionLocal() as db:
                db.execute(text("SELECT 1"))
                checks["database"] = "ok"
                checks["postgis"] = db.execute(text("SELECT postgis_lib_version()")).scalar()
                checks["migrations"] = db.execute(text("SELECT version_num FROM alembic_version")).scalar()
        except Exception as exc:  # noqa: BLE001
            checks["database"] = f"error: {type(exc).__name__}"
        checks["redis"] = "ok" if get_cache()._redis is not None else "unavailable (in-process fallback)"
        ok = checks.get("database") == "ok"
        return JSONResponse({"status": "ready" if ok else "not_ready", "checks": checks}, status_code=200 if ok else 503)

    @app.get("/metrics", tags=["system"])
    def metrics() -> Response:
        return Response(metrics_payload(), media_type="text/plain; version=0.0.4")

    @app.get("/api/system/errors", tags=["system"])
    def recent_errors(user=Depends(require(P_AUDIT))) -> dict:  # noqa: ANN001
        return {"items": list(RECENT_ERRORS)[-50:], "cache": {"hits": get_cache().hits, "misses": get_cache().misses}}

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket) -> None:
        """Auth: first message must be {"type":"auth","token":"..."} (tokens are never put in URLs)."""
        from app.auth.deps import authenticate_token

        await ws.accept()
        try:
            first = json.loads(await asyncio.wait_for(ws.receive_text(), timeout=10))
            with SessionLocal() as db:
                principal = authenticate_token(db, str(first.get("token", "")))
        except Exception:  # noqa: BLE001
            await ws.close(code=4401)
            return
        await hub.connect(ws, {"id": principal.id, "username": principal.username, "role": principal.role})
        await ws.send_text(json.dumps({"event": "ready", "user": principal.username, "topics": ["alerts"]}))
        try:
            while True:
                msg = json.loads(await ws.receive_text())
                kind, topic = msg.get("type"), str(msg.get("topic", ""))[:120]
                if kind == "subscribe" and (topic.startswith("investigation:") or topic in ("alerts", "progress")):
                    hub.subscribe(ws, topic)
                    await ws.send_text(json.dumps({"event": "subscribed", "topic": topic}))
                elif kind == "unsubscribe":
                    hub.unsubscribe(ws, topic)
                elif kind == "presence" and topic.startswith("investigation:"):
                    hub.publish(topic, "presence", {"user": principal.username, "state": str(msg.get("state", "viewing"))[:40]})
                elif kind == "ping":
                    await ws.send_text(json.dumps({"event": "pong"}))
        except (WebSocketDisconnect, ValueError, RuntimeError):
            pass
        finally:
            hub.disconnect(ws)

    return app


app = create_app()
