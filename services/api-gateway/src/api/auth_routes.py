"""
Authentication routes: register / login / refresh / me.

User records are stored in Redis (hash per user, keyed by email) when a
Redis connection is available, with an in-memory fallback for tests.
Passwords are hashed with bcrypt.
"""

import json
import os
from typing import Any, Dict, Optional

import bcrypt
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.auth_v2 import create_token_pair, decode_token, verify_token

router = APIRouter(prefix="/auth", tags=["auth"])


def _hash_password(password: str) -> str:
    # bcrypt operates on at most 72 bytes; the request model enforces
    # max_length=72 so nothing is silently truncated here.
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:
        return False

_VALID_ROLES = {"viewer", "user", "operator", "admin"}


class _UserStore:
    """Redis-backed user store with in-memory fallback."""

    def __init__(self) -> None:
        self._memory: Dict[str, Dict[str, Any]] = {}
        self._redis = None
        host = os.environ.get("REDIS_HOST")
        if host:
            try:
                import redis  # type: ignore

                self._redis = redis.Redis(
                    host=host,
                    port=int(os.environ.get("REDIS_PORT", "6379")),
                    password=os.environ.get("REDIS_PASSWORD") or None,
                    decode_responses=True,
                    socket_connect_timeout=2,
                )
                self._redis.ping()
            except Exception:
                # Redis unreachable: keep the in-memory fallback but do
                # not hide it — log loudly so operators notice.
                import logging

                logging.getLogger(__name__).warning(
                    "auth user store: Redis unreachable, using in-memory "
                    "store (users will not survive a restart)"
                )
                self._redis = None

    def _key(self, email: str) -> str:
        return f"galileo:users:{email.strip().lower()}"

    def get(self, email: str) -> Optional[Dict[str, Any]]:
        if self._redis is not None:
            raw = self._redis.get(self._key(email))
            return json.loads(raw) if raw else None
        return self._memory.get(email.strip().lower())

    def put(self, email: str, record: Dict[str, Any]) -> None:
        if self._redis is not None:
            self._redis.set(self._key(email), json.dumps(record))
        else:
            self._memory[email.strip().lower()] = record


_store = _UserStore()


class RegisterRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=72)
    full_name: str = Field(default="", max_length=255)


class LoginRequest(BaseModel):
    email: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


@router.post("/register", status_code=201)
def register(body: RegisterRequest) -> Dict[str, Any]:
    """Create a user account. First registered user becomes admin."""
    if _store.get(body.email):
        raise HTTPException(status_code=409, detail="User already exists")

    is_first = _store.get("__admin_bootstrapped__") is None
    roles = ["admin", "operator", "user"] if is_first else ["user"]

    record = {
        "user_id": body.email.strip().lower(),
        "email": body.email.strip().lower(),
        "full_name": body.full_name,
        "password_hash": _hash_password(body.password),
        "roles": roles,
    }
    _store.put(body.email, record)
    if is_first:
        _store.put("__admin_bootstrapped__", {"done": True})

    return {"user_id": record["user_id"], "email": record["email"], "roles": roles}


@router.post("/token")
def login(body: LoginRequest) -> Dict[str, Any]:
    """Issue an access/refresh token pair for valid credentials."""
    record = _store.get(body.email)
    if not record or not _verify_password(body.password, record["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return create_token_pair(
        user_id=record["user_id"], email=record["email"], roles=record["roles"]
    )


@router.post("/refresh")
def refresh(body: RefreshRequest) -> Dict[str, Any]:
    """Exchange a valid refresh token for a new token pair."""
    payload = decode_token(body.refresh_token, expected_type="refresh")
    record = _store.get(payload["email"])
    if not record:
        raise HTTPException(status_code=401, detail="Unknown user")
    return create_token_pair(
        user_id=record["user_id"], email=record["email"], roles=record["roles"]
    )


@router.get("/me")
def me(user: Dict[str, Any] = Depends(verify_token)) -> Dict[str, Any]:
    """Return the authenticated user's identity claims."""
    return {
        "user_id": user.get("user_id"),
        "email": user.get("email"),
        "roles": user.get("roles", []),
    }
