"""Authentication, sessions and user administration."""

from __future__ import annotations

import secrets
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.common import ip_of
from app.audit.service import record
from app.auth.deps import Principal, get_current_user, require
from app.auth.ratelimit import get_limiter
from app.auth.rbac import P_USERS
from app.auth.security import create_access_token, hash_password, validate_password_policy, verify_password
from app.config import get_settings
from app.db import get_db
from app.models import Role, User, UserSession, new_id, utcnow

router = APIRouter(prefix="/api/auth", tags=["auth"])
users_router = APIRouter(prefix="/api/users", tags=["users"])

MAX_FAILED = 5
LOCKOUT = timedelta(minutes=15)
_DUMMY_HASH = hash_password("timing-equaliser-not-a-real-password", rounds=4)  # noqa: S105 - never matches a login


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"  # noqa: S105 - OAuth token type, not a secret
    expires_in: int
    user: dict


@router.post("/login", response_model=LoginResponse)
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)) -> LoginResponse:
    ip = ip_of(request)
    ok, _ = get_limiter().hit(f"login:{ip}:{body.username.lower()}", get_settings().login_rate_limit_per_minute)
    if not ok:
        raise HTTPException(429, "Too many login attempts")
    user = db.scalar(select(User).where(User.username == body.username))
    now = utcnow()
    if user is None:
        verify_password(body.password, _DUMMY_HASH)  # equalise timing for unknown users
        record(db, "login_failed", None, "user", body.username, details={"reason": "unknown_user"}, ip=ip)
        db.commit()
        raise HTTPException(401, "Invalid credentials")
    if user.locked_until and user.locked_until > now:
        record(db, "login_failed", user, "user", user.id, details={"reason": "locked"}, ip=ip)
        db.commit()
        raise HTTPException(401, "Invalid credentials")
    if not user.is_active or not verify_password(body.password, user.password_hash):
        user.failed_logins += 1
        if user.failed_logins >= MAX_FAILED:
            user.locked_until = now + LOCKOUT
            user.failed_logins = 0
        record(db, "login_failed", user, "user", user.id, details={"reason": "bad_password" if user.is_active else "inactive"}, ip=ip)
        db.commit()
        raise HTTPException(401, "Invalid credentials")
    user.failed_logins = 0
    user.locked_until = None
    s = get_settings()
    sess = UserSession(id=secrets.token_hex(16), user_id=user.id, created_at=now, last_seen_at=now,
                       expires_at=now + timedelta(minutes=max(s.access_token_minutes, s.session_idle_minutes)), ip=ip,
                       user_agent=(request.headers.get("user-agent") or "")[:300])
    db.add(sess)
    token, ttl = create_access_token(user.id, user.role, sess.id)
    record(db, "login", user, "session", sess.id, ip=ip)
    db.commit()
    return LoginResponse(access_token=token, expires_in=ttl, user={"id": user.id, "username": user.username, "role": user.role,
                                                                   "display_name": user.display_name})


@router.post("/logout")
def logout(request: Request, user: Principal = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    sess = db.get(UserSession, user.session_id)
    if sess:
        sess.revoked_at = utcnow()
    record(db, "logout", user, "session", user.session_id, ip=ip_of(request))
    db.commit()
    return {"status": "logged_out"}


@router.get("/me")
def me(user: Principal = Depends(get_current_user)) -> dict:
    return {"id": user.id, "username": user.username, "role": user.role, "permissions": sorted(user.permissions)}


class UserCreate(BaseModel):
    username: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,63}$")
    display_name: str = Field(default="", max_length=200)
    password: str = Field(min_length=12, max_length=256)
    role: Role


class UserPatch(BaseModel):
    role: Role | None = None
    is_active: bool | None = None
    display_name: str | None = Field(default=None, max_length=200)


def _user_dict(u: User) -> dict:
    return {"id": u.id, "username": u.username, "display_name": u.display_name, "role": u.role, "is_active": u.is_active,
            "created_at": u.created_at.isoformat()}


@users_router.get("")
def list_users(user: Principal = Depends(require(P_USERS)), db: Session = Depends(get_db)) -> list[dict]:
    return [_user_dict(u) for u in db.scalars(select(User).order_by(User.username))]


@users_router.post("", status_code=201)
def create_user(body: UserCreate, request: Request, user: Principal = Depends(require(P_USERS)), db: Session = Depends(get_db)) -> dict:
    try:
        validate_password_policy(body.password)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if db.scalar(select(User).where(User.username == body.username)):
        raise HTTPException(409, "username exists")
    u = User(id=new_id("usr"), username=body.username, display_name=body.display_name, password_hash=hash_password(body.password), role=body.role.value)
    db.add(u)
    db.flush()
    record(db, "user_admin", user, "user", u.id, new_value=_user_dict(u), ip=ip_of(request))
    db.commit()
    return _user_dict(u)


@users_router.patch("/{user_id}")
def patch_user(user_id: str, body: UserPatch, request: Request, user: Principal = Depends(require(P_USERS)), db: Session = Depends(get_db)) -> dict:
    u = db.get(User, user_id)
    if u is None:
        raise HTTPException(404, "user not found")
    if u.id == user.id and (body.role is not None or body.is_active is False):
        raise HTTPException(400, "administrators cannot change their own role or disable themselves")
    before = _user_dict(u)
    if body.role is not None:
        u.role = body.role.value
    if body.is_active is not None:
        u.is_active = body.is_active
        if not body.is_active:
            for s in db.scalars(select(UserSession).where(UserSession.user_id == u.id, UserSession.revoked_at.is_(None))):
                s.revoked_at = utcnow()
    if body.display_name is not None:
        u.display_name = body.display_name
    record(db, "user_admin", user, "user", u.id, previous_value=before, new_value=_user_dict(u), ip=ip_of(request))
    db.commit()
    return _user_dict(u)
