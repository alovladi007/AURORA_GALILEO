"""
Authentication and Authorization for GALILEO Main API
Provides JWT token validation and optional API key authentication
"""

import os
from datetime import datetime, timedelta
from typing import Optional
from fastapi import Depends, HTTPException, status, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, APIKeyHeader
from jose import JWTError, jwt

# Security schemes
security_bearer = HTTPBearer(auto_error=False)
security_api_key = APIKeyHeader(name="X-API-Key", auto_error=False)

# JWT Configuration
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
if not JWT_SECRET_KEY and os.getenv("ENVIRONMENT", "development") == "production":
    raise ValueError("JWT_SECRET_KEY must be set in production")

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

# API Key Configuration (for service-to-service authentication)
VALID_API_KEYS = set(
    key.strip()
    for key in os.getenv("VALID_API_KEYS", "").split(",")
    if key.strip()
)

# Development mode settings
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")
AUTH_ENABLED = os.getenv("AUTH_ENABLED", "true").lower() == "true"


def verify_jwt_token(token: str) -> dict:
    """
    Verify JWT token and return payload

    Args:
        token: JWT token string

    Returns:
        dict: Token payload containing user information

    Raises:
        HTTPException: If token is invalid
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        if not JWT_SECRET_KEY:
            # In development without JWT secret, allow but warn
            if ENVIRONMENT == "development":
                return {"sub": "dev-user", "dev_mode": True}
            raise credentials_exception

        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        return payload
    except JWTError:
        raise credentials_exception


def verify_api_key(api_key: str) -> bool:
    """
    Verify API key for service-to-service authentication

    Args:
        api_key: API key string

    Returns:
        bool: True if API key is valid
    """
    return api_key in VALID_API_KEYS if VALID_API_KEYS else False


async def get_current_user(
    bearer_credentials: Optional[HTTPAuthorizationCredentials] = Security(security_bearer),
    api_key: Optional[str] = Security(security_api_key),
) -> dict:
    """
    Dependency to get current authenticated user from JWT or API key

    Args:
        bearer_credentials: Bearer token from Authorization header
        api_key: API key from X-API-Key header

    Returns:
        dict: User information from token payload or API key

    Raises:
        HTTPException: If authentication fails
    """
    # Skip authentication in development if disabled
    if not AUTH_ENABLED and ENVIRONMENT == "development":
        return {"sub": "dev-user", "dev_mode": True, "roles": ["admin"]}

    # Try API key authentication first
    if api_key and verify_api_key(api_key):
        return {"sub": "api-service", "auth_type": "api_key", "roles": ["service"]}

    # Try JWT bearer token authentication
    if bearer_credentials:
        return verify_jwt_token(bearer_credentials.credentials)

    # No valid authentication provided
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No valid authentication credentials provided",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_active_user(
    current_user: dict = Depends(get_current_user)
) -> dict:
    """
    Dependency to get current active user (non-disabled)

    Args:
        current_user: User from get_current_user dependency

    Returns:
        dict: Active user information

    Raises:
        HTTPException: If user is inactive
    """
    if current_user.get("disabled"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Inactive user"
        )
    return current_user


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a new JWT access token

    Args:
        data: Payload data to encode in token
        expires_delta: Optional custom expiration time

    Returns:
        str: Encoded JWT token
    """
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})

    if not JWT_SECRET_KEY:
        raise ValueError("JWT_SECRET_KEY not configured")

    encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


# Optional: Role-based access control
def require_role(required_role: str):
    """
    Dependency factory for role-based access control

    Args:
        required_role: Required role name

    Returns:
        Dependency function that checks user role
    """
    async def role_checker(current_user: dict = Depends(get_current_user)) -> dict:
        user_roles = current_user.get("roles", [])
        if required_role not in user_roles and "admin" not in user_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required role: {required_role}"
            )
        return current_user
    return role_checker
