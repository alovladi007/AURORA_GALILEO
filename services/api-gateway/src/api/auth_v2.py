"""
Authentication core for the API Gateway.

- Signing key comes from the JWT_SECRET environment variable. A
  hardcoded fallback is used ONLY when AUTH_MODE=optional (development);
  otherwise a missing secret is a startup error.
- Token verification is strict by default: a missing or invalid token
  is a 401. In AUTH_MODE=optional (development), requests with NO
  Authorization header act as an anonymous viewer — but an invalid or
  expired token is still always a 401 (silent fallback to anonymous on
  bad credentials was a security hole).
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from fastapi import Header, HTTPException
from jose import JWTError, jwt

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7

AUTH_MODE = os.environ.get("AUTH_MODE", "required").lower()
_DEV_ONLY_SECRET = "dev-only-secret-do-not-deploy"


def _resolve_secret() -> str:
    secret = os.environ.get("JWT_SECRET")
    if secret:
        return secret
    if AUTH_MODE == "optional":
        return _DEV_ONLY_SECRET
    raise RuntimeError(
        "JWT_SECRET is not set. Set the JWT_SECRET environment variable, "
        "or set AUTH_MODE=optional for local development."
    )


SECRET_KEY = _resolve_secret()

ANONYMOUS_USER = {
    "user_id": "anonymous",
    "email": "anonymous@galileo.dev",
    "roles": ["viewer"],
}


def create_token_pair(user_id: str, email: str, roles: Optional[list] = None) -> Dict[str, Any]:
    """Create an access/refresh token pair."""
    if roles is None:
        roles = ["user"]

    now = datetime.now(timezone.utc)
    access_token = jwt.encode(
        {
            "user_id": user_id,
            "email": email,
            "roles": roles,
            "type": "access",
            "exp": now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
        },
        SECRET_KEY,
        algorithm=ALGORITHM,
    )
    refresh_token = jwt.encode(
        {
            "user_id": user_id,
            "email": email,
            "type": "refresh",
            "exp": now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
        },
        SECRET_KEY,
        algorithm=ALGORITHM,
    )

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


def decode_token(token: str, expected_type: str = "access") -> Dict[str, Any]:
    """Decode and validate a JWT; raises HTTPException on any failure."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid token: {exc}")
    if payload.get("type") != expected_type:
        raise HTTPException(status_code=401, detail="Invalid token type")
    return payload


def verify_token(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    """FastAPI dependency: verify the Authorization header.

    Strict: invalid/expired tokens are always 401. A missing header is
    401 unless AUTH_MODE=optional (development), where it resolves to
    the anonymous viewer.
    """
    if not authorization:
        if AUTH_MODE == "optional":
            return dict(ANONYMOUS_USER)
        raise HTTPException(
            status_code=401, detail="Missing Authorization header"
        )

    token = authorization[7:] if authorization.startswith("Bearer ") else authorization
    return decode_token(token, expected_type="access")
