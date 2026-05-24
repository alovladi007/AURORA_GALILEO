"""
Enhanced JWT Authentication for GALILEO V2.0

Production-grade authentication with:
- Short-lived access tokens (15 min)
- Long-lived refresh tokens (7 days)
- Token rotation on refresh
- JWT blacklist for revocation (Redis-backed)
- Device fingerprinting
- Brute force protection
- Account lockout
- Authentication event logging
"""

import os
import hashlib
import secrets
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from enum import Enum

from fastapi import Depends, HTTPException, status, Request, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
from pydantic import BaseModel
import redis.asyncio as redis

logger = logging.getLogger(__name__)

# ============================================================================
# Configuration
# ============================================================================

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
JWT_REFRESH_SECRET_KEY = os.getenv("JWT_REFRESH_SECRET_KEY", JWT_SECRET_KEY)

if not JWT_SECRET_KEY and os.getenv("ENVIRONMENT") == "production":
    raise ValueError("JWT_SECRET_KEY must be set in production")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

# Brute force protection
MAX_LOGIN_ATTEMPTS = int(os.getenv("MAX_LOGIN_ATTEMPTS", "5"))
LOCKOUT_DURATION_MINUTES = int(os.getenv("LOCKOUT_DURATION_MINUTES", "30"))

# Redis connection for blacklist and rate limiting
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
_redis_client: Optional[redis.Redis] = None


async def get_redis() -> redis.Redis:
    """Get or create Redis connection"""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    return _redis_client


# ============================================================================
# Token Types
# ============================================================================

class TokenType(str, Enum):
    ACCESS = "access"
    REFRESH = "refresh"


class TokenPair(BaseModel):
    """Response model for token pair"""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class TokenPayload(BaseModel):
    """Token payload structure"""
    sub: str  # subject (user id)
    type: TokenType
    jti: str  # JWT ID for tracking
    iat: int  # issued at
    exp: int  # expiration
    device_id: Optional[str] = None
    roles: list[str] = []


# ============================================================================
# Token Generation
# ============================================================================

def _generate_jti() -> str:
    """Generate unique JWT ID"""
    return secrets.token_urlsafe(16)


def create_access_token(
    user_id: str,
    roles: list[str] = None,
    device_id: Optional[str] = None,
    expires_delta: Optional[timedelta] = None,
) -> tuple[str, str]:
    """
    Create JWT access token.

    Args:
        user_id: User identifier (subject)
        roles: User roles
        device_id: Optional device fingerprint
        expires_delta: Custom expiration

    Returns:
        (token, jti) tuple
    """
    jti = _generate_jti()
    now = datetime.utcnow()
    expire = now + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))

    payload = {
        "sub": user_id,
        "type": TokenType.ACCESS.value,
        "jti": jti,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "roles": roles or [],
    }

    if device_id:
        payload["device_id"] = device_id

    token = jwt.encode(payload, JWT_SECRET_KEY, algorithm=ALGORITHM)
    return token, jti


def create_refresh_token(
    user_id: str,
    device_id: Optional[str] = None,
) -> tuple[str, str]:
    """
    Create JWT refresh token.

    Args:
        user_id: User identifier
        device_id: Optional device fingerprint

    Returns:
        (token, jti) tuple
    """
    jti = _generate_jti()
    now = datetime.utcnow()
    expire = now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

    payload = {
        "sub": user_id,
        "type": TokenType.REFRESH.value,
        "jti": jti,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }

    if device_id:
        payload["device_id"] = device_id

    token = jwt.encode(payload, JWT_REFRESH_SECRET_KEY, algorithm=ALGORITHM)
    return token, jti


async def create_token_pair(
    user_id: str,
    roles: list[str] = None,
    device_id: Optional[str] = None,
) -> TokenPair:
    """
    Create access and refresh token pair.

    Args:
        user_id: User identifier
        roles: User roles
        device_id: Optional device fingerprint

    Returns:
        TokenPair with access and refresh tokens
    """
    access_token, access_jti = create_access_token(user_id, roles, device_id)
    refresh_token, refresh_jti = create_refresh_token(user_id, device_id)

    # Store refresh token JTI in Redis for tracking
    r = await get_redis()
    await r.setex(
        f"refresh_token:{refresh_jti}",
        REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        user_id,
    )

    # Log authentication event
    logger.info(f"Token pair created for user={user_id}, device={device_id}")

    return TokenPair(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


# ============================================================================
# Token Verification
# ============================================================================

async def verify_token(
    token: str,
    expected_type: TokenType = TokenType.ACCESS,
) -> Dict[str, Any]:
    """
    Verify JWT token with blacklist check.

    Args:
        token: JWT token string
        expected_type: Expected token type

    Returns:
        Token payload

    Raises:
        HTTPException: If token is invalid, expired, or blacklisted
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        # Choose secret based on expected type
        secret = JWT_REFRESH_SECRET_KEY if expected_type == TokenType.REFRESH else JWT_SECRET_KEY

        payload = jwt.decode(token, secret, algorithms=[ALGORITHM])

        # Verify token type
        if payload.get("type") != expected_type.value:
            logger.warning(f"Token type mismatch: expected={expected_type.value}, got={payload.get('type')}")
            raise credentials_exception

        # Check blacklist
        jti = payload.get("jti")
        if jti and await is_token_blacklisted(jti):
            logger.warning(f"Blacklisted token used: jti={jti}")
            raise credentials_exception

        return payload

    except JWTError as e:
        logger.warning(f"JWT validation failed: {e}")
        raise credentials_exception


# ============================================================================
# Token Blacklist (Revocation)
# ============================================================================

async def blacklist_token(jti: str, exp: int) -> None:
    """
    Add token to blacklist.

    Args:
        jti: JWT ID
        exp: Token expiration timestamp
    """
    r = await get_redis()

    # Calculate TTL (until token would naturally expire)
    ttl = max(int(exp - datetime.utcnow().timestamp()), 1)

    await r.setex(f"blacklist:{jti}", ttl, "1")
    logger.info(f"Token blacklisted: jti={jti}, ttl={ttl}s")


async def is_token_blacklisted(jti: str) -> bool:
    """Check if token is blacklisted"""
    r = await get_redis()
    return await r.exists(f"blacklist:{jti}") > 0


async def revoke_token(token: str, token_type: TokenType = TokenType.ACCESS) -> bool:
    """
    Revoke a token by adding to blacklist.

    Args:
        token: Token to revoke
        token_type: Type of token

    Returns:
        True if revoked successfully
    """
    try:
        secret = JWT_REFRESH_SECRET_KEY if token_type == TokenType.REFRESH else JWT_SECRET_KEY
        payload = jwt.decode(token, secret, algorithms=[ALGORITHM], options={"verify_exp": False})

        jti = payload.get("jti")
        exp = payload.get("exp")

        if jti and exp:
            await blacklist_token(jti, exp)
            return True
        return False

    except JWTError:
        return False


async def revoke_all_user_tokens(user_id: str) -> int:
    """
    Revoke all tokens for a user.
    Used when password changes, account compromise, etc.

    Args:
        user_id: User identifier

    Returns:
        Number of tokens revoked
    """
    r = await get_redis()

    # Find all refresh tokens for user
    revoked_count = 0
    async for key in r.scan_iter(match="refresh_token:*"):
        stored_user_id = await r.get(key)
        if stored_user_id == user_id:
            jti = key.split(":", 1)[1]
            await r.setex(f"blacklist:{jti}", 7 * 86400, "1")
            await r.delete(key)
            revoked_count += 1

    logger.info(f"Revoked {revoked_count} tokens for user={user_id}")
    return revoked_count


# ============================================================================
# Token Refresh & Rotation
# ============================================================================

async def refresh_access_token(refresh_token: str) -> TokenPair:
    """
    Refresh access token using refresh token.
    Implements token rotation - old refresh token is invalidated.

    Args:
        refresh_token: Valid refresh token

    Returns:
        New token pair

    Raises:
        HTTPException: If refresh token is invalid
    """
    # Verify refresh token
    payload = await verify_token(refresh_token, expected_type=TokenType.REFRESH)

    user_id = payload["sub"]
    device_id = payload.get("device_id")
    old_jti = payload["jti"]

    # Get user roles (would typically come from database)
    roles = payload.get("roles", [])

    # Blacklist old refresh token (rotation)
    await blacklist_token(old_jti, payload["exp"])

    # Remove from active refresh tokens
    r = await get_redis()
    await r.delete(f"refresh_token:{old_jti}")

    # Create new token pair
    new_tokens = await create_token_pair(user_id, roles, device_id)

    logger.info(f"Token refreshed for user={user_id}, old_jti={old_jti}")

    return new_tokens


# ============================================================================
# Brute Force Protection
# ============================================================================

async def check_account_lockout(identifier: str) -> bool:
    """
    Check if account is locked due to too many failed attempts.

    Args:
        identifier: User identifier (email, username, IP)

    Returns:
        True if locked
    """
    r = await get_redis()
    locked = await r.get(f"lockout:{identifier}")
    return locked is not None


async def record_failed_login(identifier: str) -> int:
    """
    Record failed login attempt.

    Args:
        identifier: User identifier

    Returns:
        Current attempt count
    """
    r = await get_redis()

    # Increment counter
    key = f"login_attempts:{identifier}"
    count = await r.incr(key)

    # Set expiry on first attempt
    if count == 1:
        await r.expire(key, LOCKOUT_DURATION_MINUTES * 60)

    # Lock account if threshold reached
    if count >= MAX_LOGIN_ATTEMPTS:
        await r.setex(
            f"lockout:{identifier}",
            LOCKOUT_DURATION_MINUTES * 60,
            "1",
        )
        logger.warning(
            f"Account locked: identifier={identifier}, attempts={count}, "
            f"duration={LOCKOUT_DURATION_MINUTES}min"
        )

    return count


async def clear_failed_logins(identifier: str) -> None:
    """Clear failed login attempts after successful login"""
    r = await get_redis()
    await r.delete(f"login_attempts:{identifier}")
    await r.delete(f"lockout:{identifier}")


# ============================================================================
# Device Fingerprinting
# ============================================================================

def generate_device_fingerprint(request: Request) -> str:
    """
    Generate device fingerprint from request headers.
    Helps detect suspicious token usage.

    Args:
        request: FastAPI Request

    Returns:
        Device fingerprint hash
    """
    components = [
        request.headers.get("user-agent", ""),
        request.headers.get("accept-language", ""),
        request.headers.get("accept-encoding", ""),
        request.client.host if request.client else "",
    ]
    fingerprint_data = "|".join(components)
    return hashlib.sha256(fingerprint_data.encode()).hexdigest()[:16]


# ============================================================================
# FastAPI Dependencies
# ============================================================================

security_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security_bearer),
) -> Dict[str, Any]:
    """
    Get current authenticated user from JWT token.

    Args:
        request: FastAPI request
        credentials: Bearer token credentials

    Returns:
        User information

    Raises:
        HTTPException: If authentication fails
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = await verify_token(credentials.credentials, TokenType.ACCESS)

    # Verify device fingerprint matches (optional security enhancement)
    if "device_id" in payload:
        current_fingerprint = generate_device_fingerprint(request)
        if payload["device_id"] != current_fingerprint:
            logger.warning(
                f"Device fingerprint mismatch: user={payload['sub']}, "
                f"expected={payload['device_id']}, got={current_fingerprint}"
            )
            # Optionally raise exception or just log

    return payload


async def get_current_active_user(
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """Get active (non-disabled) user"""
    if current_user.get("disabled"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Account is disabled",
        )
    return current_user
