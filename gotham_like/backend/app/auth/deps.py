"""FastAPI dependencies: authentication, session validation, permission checks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.audit.service import record
from app.auth.rbac import has_permission, permissions_for
from app.auth.security import decode_access_token
from app.config import get_settings
from app.db import get_db
from app.models import User, UserSession, utcnow
from app.observability import user_var

bearer = HTTPBearer(auto_error=False)


@dataclass
class Principal:
    id: str
    username: str
    role: str
    session_id: str

    @property
    def permissions(self) -> frozenset[str]:
        return permissions_for(self.role)

    def can(self, permission: str) -> bool:
        return has_permission(self.role, permission)


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _unauthorized(detail: str = "Not authenticated") -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, detail, headers={"WWW-Authenticate": "Bearer"})


def authenticate_token(db: Session, token: str) -> Principal:
    try:
        claims = decode_access_token(token)
    except jwt.PyJWTError as exc:
        raise _unauthorized("Invalid or expired token") from exc
    sess = db.get(UserSession, claims["sid"])
    now = utcnow()
    idle = timedelta(minutes=get_settings().session_idle_minutes)
    if sess is None or sess.revoked_at is not None or sess.expires_at < now or now - sess.last_seen_at > idle:
        raise _unauthorized("Session expired or revoked")
    user = db.get(User, claims["sub"])
    if user is None or not user.is_active or user.id != sess.user_id:
        raise _unauthorized("User disabled")
    if (now - sess.last_seen_at).total_seconds() > 30:
        sess.last_seen_at = now
        db.commit()
    # role is always read from the database, never trusted from the token
    return Principal(id=user.id, username=user.username, role=user.role, session_id=sess.id)


def get_current_user(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> Principal:
    if creds is None or creds.scheme.lower() != "bearer":
        raise _unauthorized()
    principal = authenticate_token(db, creds.credentials)
    user_var.set(principal.username)
    request.state.principal = principal
    return principal


def require(permission: str):  # noqa: ANN201
    def checker(request: Request, user: Principal = Depends(get_current_user), db: Session = Depends(get_db)) -> Principal:
        if not user.can(permission):
            record(db, "access_denied", user, details={"permission": permission, "path": request.url.path}, ip=client_ip(request))
            db.commit()
            raise HTTPException(status.HTTP_403_FORBIDDEN, f"Missing permission: {permission}")
        return user

    return checker
