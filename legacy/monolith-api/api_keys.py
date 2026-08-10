"""
API Key Management for GALILEO Platform

Production-grade API key system with:
- Cryptographically secure key generation
- Scope-based authorization
- Usage tracking
- Key rotation
- Expiration management
- Rate limiting per key
"""

import secrets
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Set, Dict, Any
from enum import Enum

from fastapi import Depends, HTTPException, status, Security, Request
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field
import redis.asyncio as redis

logger = logging.getLogger(__name__)


# ============================================================================
# Configuration
# ============================================================================

API_KEY_HEADER_NAME = "X-API-Key"
API_KEY_PREFIX = "glo_"  # GALILEO Operations
API_KEY_LENGTH = 32  # bytes -> 43 chars base64

# Default rate limits per scope
DEFAULT_RATE_LIMITS = {
    "read": 1000,  # 1000 requests per minute
    "write": 100,  # 100 requests per minute
    "admin": 50,   # 50 requests per minute
}


# ============================================================================
# Scopes
# ============================================================================

class APIKeyScope(str, Enum):
    """API key scopes for fine-grained access control"""

    # Read scopes
    READ_DATA = "read:data"
    READ_MODELS = "read:models"
    READ_SIMULATIONS = "read:simulations"
    READ_WORKFLOWS = "read:workflows"
    READ_SATELLITE = "read:satellite"
    READ_ALL = "read:*"

    # Write scopes
    WRITE_DATA = "write:data"
    WRITE_MODELS = "write:models"
    WRITE_SIMULATIONS = "write:simulations"
    WRITE_WORKFLOWS = "write:workflows"
    WRITE_ALL = "write:*"

    # Admin scopes
    ADMIN_USERS = "admin:users"
    ADMIN_SYSTEM = "admin:system"
    ADMIN_ALL = "admin:*"

    # Special
    FULL_ACCESS = "*"


# ============================================================================
# Data Models
# ============================================================================

class APIKeyCreate(BaseModel):
    """Request model for creating API key"""
    name: str = Field(..., min_length=3, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    scopes: List[APIKeyScope] = Field(default_factory=lambda: [APIKeyScope.READ_ALL])
    expires_at: Optional[datetime] = None
    rate_limit_per_minute: Optional[int] = None


class APIKeyInfo(BaseModel):
    """API key information (without the actual key)"""
    key_id: str
    name: str
    description: Optional[str]
    scopes: List[APIKeyScope]
    created_at: datetime
    expires_at: Optional[datetime]
    last_used_at: Optional[datetime]
    usage_count: int = 0
    rate_limit_per_minute: int
    is_active: bool


class APIKeyResponse(BaseModel):
    """Response when creating new API key (includes actual key)"""
    key_id: str
    api_key: str  # Only shown once!
    name: str
    scopes: List[APIKeyScope]
    expires_at: Optional[datetime]
    warning: str = "Save this API key now. You won't be able to see it again."


# ============================================================================
# Redis Connection (shared with auth_v2)
# ============================================================================

import os
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
_redis_client: Optional[redis.Redis] = None


async def get_redis() -> redis.Redis:
    """Get Redis connection"""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    return _redis_client


# ============================================================================
# Key Generation
# ============================================================================

def generate_api_key() -> tuple[str, str, str]:
    """
    Generate cryptographically secure API key.

    Returns:
        (key_id, raw_key, hashed_key)
    """
    # Generate random key
    random_bytes = secrets.token_bytes(API_KEY_LENGTH)
    raw_key = API_KEY_PREFIX + secrets.token_urlsafe(API_KEY_LENGTH)

    # Generate key ID (first part is identifier, hash for storage)
    key_id = "key_" + secrets.token_hex(8)

    # Hash the key for storage (never store raw keys)
    hashed_key = hash_api_key(raw_key)

    return key_id, raw_key, hashed_key


def hash_api_key(api_key: str) -> str:
    """Hash API key for storage using SHA-256"""
    return hashlib.sha256(api_key.encode()).hexdigest()


# ============================================================================
# Key Management
# ============================================================================

class APIKeyManager:
    """Manage API key lifecycle"""

    @staticmethod
    async def create_key(
        owner_id: str,
        request: APIKeyCreate,
    ) -> APIKeyResponse:
        """
        Create new API key.

        Args:
            owner_id: User ID creating the key
            request: Key creation request

        Returns:
            APIKeyResponse with actual key (only shown once)
        """
        # Generate key
        key_id, raw_key, hashed_key = generate_api_key()

        # Calculate rate limit
        rate_limit = request.rate_limit_per_minute
        if rate_limit is None:
            # Default based on highest scope
            if APIKeyScope.ADMIN_ALL in request.scopes or APIKeyScope.FULL_ACCESS in request.scopes:
                rate_limit = DEFAULT_RATE_LIMITS["admin"]
            elif any("write" in s.value for s in request.scopes):
                rate_limit = DEFAULT_RATE_LIMITS["write"]
            else:
                rate_limit = DEFAULT_RATE_LIMITS["read"]

        # Store key metadata
        key_data = {
            "key_id": key_id,
            "hashed_key": hashed_key,
            "owner_id": owner_id,
            "name": request.name,
            "description": request.description or "",
            "scopes": [s.value for s in request.scopes],
            "created_at": datetime.utcnow().isoformat(),
            "expires_at": request.expires_at.isoformat() if request.expires_at else None,
            "rate_limit_per_minute": rate_limit,
            "is_active": True,
            "usage_count": 0,
        }

        r = await get_redis()

        # Store key data
        await r.hset(f"apikey:{key_id}", mapping={
            k: str(v) if not isinstance(v, list) else ",".join(map(str, v))
            for k, v in key_data.items()
            if v is not None
        })

        # Store hash -> key_id mapping for fast lookup
        await r.set(f"apikey_hash:{hashed_key}", key_id)

        # Add to user's keys list
        await r.sadd(f"user_apikeys:{owner_id}", key_id)

        # Set expiration if specified
        if request.expires_at:
            ttl = int((request.expires_at - datetime.utcnow()).total_seconds())
            if ttl > 0:
                await r.expire(f"apikey:{key_id}", ttl)

        logger.info(
            f"API key created: key_id={key_id}, owner={owner_id}, "
            f"scopes={[s.value for s in request.scopes]}"
        )

        return APIKeyResponse(
            key_id=key_id,
            api_key=raw_key,
            name=request.name,
            scopes=request.scopes,
            expires_at=request.expires_at,
        )

    @staticmethod
    async def get_key_info(key_id: str) -> Optional[APIKeyInfo]:
        """Get API key information"""
        r = await get_redis()
        data = await r.hgetall(f"apikey:{key_id}")

        if not data:
            return None

        return APIKeyInfo(
            key_id=data["key_id"],
            name=data["name"],
            description=data.get("description") or None,
            scopes=[APIKeyScope(s) for s in data["scopes"].split(",")],
            created_at=datetime.fromisoformat(data["created_at"]),
            expires_at=datetime.fromisoformat(data["expires_at"]) if data.get("expires_at") else None,
            last_used_at=datetime.fromisoformat(data["last_used_at"]) if data.get("last_used_at") else None,
            usage_count=int(data.get("usage_count", 0)),
            rate_limit_per_minute=int(data["rate_limit_per_minute"]),
            is_active=data.get("is_active", "True") == "True",
        )

    @staticmethod
    async def list_user_keys(owner_id: str) -> List[APIKeyInfo]:
        """List all API keys for a user"""
        r = await get_redis()
        key_ids = await r.smembers(f"user_apikeys:{owner_id}")

        keys = []
        for key_id in key_ids:
            info = await APIKeyManager.get_key_info(key_id)
            if info:
                keys.append(info)

        return sorted(keys, key=lambda k: k.created_at, reverse=True)

    @staticmethod
    async def revoke_key(key_id: str, owner_id: Optional[str] = None) -> bool:
        """
        Revoke an API key.

        Args:
            key_id: Key to revoke
            owner_id: If specified, verify owner

        Returns:
            True if revoked
        """
        r = await get_redis()
        data = await r.hgetall(f"apikey:{key_id}")

        if not data:
            return False

        # Verify ownership if specified
        if owner_id and data.get("owner_id") != owner_id:
            return False

        # Mark inactive
        await r.hset(f"apikey:{key_id}", "is_active", "False")

        # Remove hash mapping (prevents future use)
        if "hashed_key" in data:
            await r.delete(f"apikey_hash:{data['hashed_key']}")

        logger.info(f"API key revoked: key_id={key_id}")
        return True

    @staticmethod
    async def rotate_key(key_id: str, owner_id: str) -> Optional[APIKeyResponse]:
        """
        Rotate an API key (generate new key, keep same permissions).

        Args:
            key_id: Key to rotate
            owner_id: Owner ID for verification

        Returns:
            New API key response or None if not found
        """
        # Get existing key info
        info = await APIKeyManager.get_key_info(key_id)
        if not info:
            return None

        # Verify ownership
        r = await get_redis()
        data = await r.hgetall(f"apikey:{key_id}")
        if data.get("owner_id") != owner_id:
            return None

        # Revoke old key
        await APIKeyManager.revoke_key(key_id, owner_id)

        # Create new key with same settings
        new_request = APIKeyCreate(
            name=info.name + " (rotated)",
            description=info.description,
            scopes=info.scopes,
            expires_at=info.expires_at,
            rate_limit_per_minute=info.rate_limit_per_minute,
        )

        return await APIKeyManager.create_key(owner_id, new_request)


# ============================================================================
# Key Validation
# ============================================================================

class APIKeyValidator:
    """Validate API keys for requests"""

    @staticmethod
    async def validate_key(api_key: str) -> Optional[Dict[str, Any]]:
        """
        Validate API key and return key data.

        Args:
            api_key: Raw API key

        Returns:
            Key data if valid, None otherwise
        """
        if not api_key or not api_key.startswith(API_KEY_PREFIX):
            return None

        # Hash the key
        hashed_key = hash_api_key(api_key)

        # Look up by hash
        r = await get_redis()
        key_id = await r.get(f"apikey_hash:{hashed_key}")

        if not key_id:
            return None

        # Get key data
        data = await r.hgetall(f"apikey:{key_id}")

        if not data:
            return None

        # Check if active
        if data.get("is_active") != "True":
            return None

        # Check expiration
        if data.get("expires_at"):
            expires_at = datetime.fromisoformat(data["expires_at"])
            if datetime.utcnow() > expires_at:
                logger.warning(f"Expired API key used: {key_id}")
                return None

        return data

    @staticmethod
    async def check_rate_limit(key_id: str, rate_limit: int) -> bool:
        """
        Check if key is within rate limit.

        Args:
            key_id: API key ID
            rate_limit: Requests per minute limit

        Returns:
            True if within limit
        """
        r = await get_redis()
        key = f"rate_limit:{key_id}:{datetime.utcnow().strftime('%Y%m%d%H%M')}"

        current = await r.incr(key)
        if current == 1:
            await r.expire(key, 60)

        return current <= rate_limit

    @staticmethod
    async def record_usage(key_id: str) -> None:
        """Record API key usage"""
        r = await get_redis()

        # Increment usage counter
        await r.hincrby(f"apikey:{key_id}", "usage_count", 1)

        # Update last used timestamp
        await r.hset(
            f"apikey:{key_id}",
            "last_used_at",
            datetime.utcnow().isoformat(),
        )


# ============================================================================
# FastAPI Dependencies
# ============================================================================

api_key_header = APIKeyHeader(name=API_KEY_HEADER_NAME, auto_error=False)


async def get_api_key_user(
    api_key: Optional[str] = Security(api_key_header),
) -> Dict[str, Any]:
    """
    Dependency to authenticate via API key.

    Returns:
        User information from API key
    """
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API key required",
            headers={"X-API-Key": "required"},
        )

    # Validate key
    key_data = await APIKeyValidator.validate_key(api_key)
    if not key_data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired API key",
        )

    # Check rate limit
    key_id = key_data["key_id"]
    rate_limit = int(key_data["rate_limit_per_minute"])

    if not await APIKeyValidator.check_rate_limit(key_id, rate_limit):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded ({rate_limit}/min)",
            headers={"Retry-After": "60"},
        )

    # Record usage
    await APIKeyValidator.record_usage(key_id)

    # Return user info
    return {
        "sub": key_data["owner_id"],
        "auth_type": "api_key",
        "key_id": key_id,
        "scopes": key_data["scopes"].split(","),
    }


def require_scope(*required_scopes: APIKeyScope):
    """
    Require specific API key scopes.

    Usage:
        @app.get("/api/data")
        async def get_data(
            user: dict = Depends(require_scope(APIKeyScope.READ_DATA))
        ):
            ...
    """
    async def scope_dependency(
        user: dict = Depends(get_api_key_user)
    ) -> dict:
        user_scopes = set(user.get("scopes", []))
        required = {s.value for s in required_scopes}

        # Full access scope grants everything
        if APIKeyScope.FULL_ACCESS.value in user_scopes:
            return user

        # Check wildcard scopes
        for scope in required:
            scope_prefix = scope.split(":")[0] + ":*"  # e.g., "read:*"
            if scope_prefix in user_scopes:
                continue
            if scope not in user_scopes:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Required scope: {scope}",
                )

        return user

    return scope_dependency
