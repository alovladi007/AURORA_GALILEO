"""
Authentication module for API Gateway
Simplified version for development
"""

from typing import Optional, Dict, Any
from datetime import datetime, timedelta
import jwt
from fastapi import HTTPException, Header

SECRET_KEY = "dev-secret-key-change-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7


def create_token_pair(user_id: str, email: str, roles: list = None) -> Dict[str, str]:
    """Create access and refresh tokens"""
    if roles is None:
        roles = ["user"]

    access_token_data = {
        "user_id": user_id,
        "email": email,
        "roles": roles,
        "type": "access",
        "exp": datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    }

    refresh_token_data = {
        "user_id": user_id,
        "email": email,
        "type": "refresh",
        "exp": datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
    }

    access_token = jwt.encode(access_token_data, SECRET_KEY, algorithm=ALGORITHM)
    refresh_token = jwt.encode(refresh_token_data, SECRET_KEY, algorithm=ALGORITHM)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60
    }


def verify_token(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    """Verify JWT token and return user data"""
    if not authorization:
        # Allow unauthenticated access for development
        return {
            "user_id": "anonymous",
            "email": "anonymous@galileo.dev",
            "roles": ["user"]
        }

    try:
        # Extract token from "Bearer <token>"
        if authorization.startswith("Bearer "):
            token = authorization[7:]
        else:
            token = authorization

        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

        if payload.get("type") != "access":
            raise HTTPException(status_code=401, detail="Invalid token type")

        return payload

    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.JWTError:
        # Allow unauthenticated for development
        return {
            "user_id": "anonymous",
            "email": "anonymous@galileo.dev",
            "roles": ["user"]
        }
