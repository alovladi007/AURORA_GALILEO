"""
CSRF Protection Middleware

Implements double-submit cookie pattern for Cross-Site Request Forgery protection.
"""

import secrets
import hmac
import hashlib
from typing import Optional
from fastapi import Request, HTTPException, status
from fastapi.responses import Response
import logging

logger = logging.getLogger(__name__)

# CSRF configuration
CSRF_TOKEN_LENGTH = 32
CSRF_COOKIE_NAME = "csrf_token"
CSRF_HEADER_NAME = "X-CSRF-Token"
CSRF_SECRET_KEY = secrets.token_urlsafe(32)  # In production, load from env


class CSRFProtection:
    """
    CSRF Protection using double-submit cookie pattern.

    How it works:
    1. Server generates random token and sets it in cookie
    2. Client must include same token in request header
    3. Server validates that cookie matches header
    """

    def __init__(self, secret_key: Optional[str] = None):
        self.secret_key = secret_key or CSRF_SECRET_KEY

    def generate_token(self) -> str:
        """Generate a new CSRF token"""
        return secrets.token_urlsafe(CSRF_TOKEN_LENGTH)

    def _sign_token(self, token: str) -> str:
        """Sign token with HMAC for additional security"""
        signature = hmac.new(
            self.secret_key.encode(),
            token.encode(),
            hashlib.sha256
        ).hexdigest()
        return f"{token}.{signature}"

    def _verify_signature(self, signed_token: str) -> Optional[str]:
        """Verify and extract token from signed token"""
        try:
            token, signature = signed_token.rsplit('.', 1)
            expected_signature = hmac.new(
                self.secret_key.encode(),
                token.encode(),
                hashlib.sha256
            ).hexdigest()

            if hmac.compare_digest(signature, expected_signature):
                return token
            return None
        except (ValueError, AttributeError):
            return None

    def set_csrf_cookie(self, response: Response) -> str:
        """
        Generate and set CSRF token cookie.

        Args:
            response: FastAPI response object

        Returns:
            The generated token (for use in templates)
        """
        token = self.generate_token()
        signed_token = self._sign_token(token)

        response.set_cookie(
            key=CSRF_COOKIE_NAME,
            value=signed_token,
            httponly=True,
            secure=True,  # Only send over HTTPS
            samesite='strict',  # Prevent CSRF
            max_age=3600 * 24,  # 24 hours
        )

        return token

    def validate_csrf(self, request: Request) -> bool:
        """
        Validate CSRF token from request.

        Args:
            request: FastAPI request object

        Returns:
            True if valid, False otherwise
        """
        # Get token from cookie
        cookie_token = request.cookies.get(CSRF_COOKIE_NAME)
        if not cookie_token:
            logger.warning("CSRF validation failed: No cookie token")
            return False

        # Verify signature and extract token
        cookie_value = self._verify_signature(cookie_token)
        if not cookie_value:
            logger.warning("CSRF validation failed: Invalid signature")
            return False

        # Get token from header
        header_token = request.headers.get(CSRF_HEADER_NAME)
        if not header_token:
            logger.warning("CSRF validation failed: No header token")
            return False

        # Compare tokens (constant time comparison)
        if not hmac.compare_digest(cookie_value, header_token):
            logger.warning("CSRF validation failed: Token mismatch")
            return False

        return True


# Global CSRF protection instance
csrf_protection = CSRFProtection()


def get_csrf_token(request: Request, response: Response) -> str:
    """
    Dependency to get/generate CSRF token for forms.

    Usage in endpoint:
        @app.get("/form")
        def show_form(csrf_token: str = Depends(get_csrf_token)):
            return {"csrf_token": csrf_token}
    """
    # Check if token already exists
    existing_token = request.cookies.get(CSRF_COOKIE_NAME)
    if existing_token:
        token = csrf_protection._verify_signature(existing_token)
        if token:
            return token

    # Generate new token
    return csrf_protection.set_csrf_cookie(response)


def require_csrf_token(request: Request):
    """
    Dependency to validate CSRF token on state-changing requests.

    Usage in endpoint:
        @app.post("/api/data")
        def create_data(data: dict, _: None = Depends(require_csrf_token)):
            ...
    """
    if not csrf_protection.validate_csrf(request):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF validation failed"
        )


async def csrf_middleware(request: Request, call_next):
    """
    Middleware to automatically validate CSRF on state-changing requests.

    Validates CSRF for: POST, PUT, DELETE, PATCH
    Skips validation for: GET, HEAD, OPTIONS
    """
    # Skip CSRF validation for safe methods
    if request.method in ["GET", "HEAD", "OPTIONS"]:
        return await call_next(request)

    # Skip CSRF validation for API endpoints using other auth methods
    # (e.g., Bearer tokens, API keys)
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return await call_next(request)

    # Skip for specific paths (health checks, metrics, etc.)
    skip_paths = ["/health", "/metrics", "/docs", "/openapi.json", "/redoc"]
    if any(request.url.path.startswith(path) for path in skip_paths):
        return await call_next(request)

    # Validate CSRF token
    if not csrf_protection.validate_csrf(request):
        logger.warning(
            f"CSRF validation failed for {request.method} {request.url.path} "
            f"from {request.client.host if request.client else 'unknown'}"
        )
        return Response(
            content='{"detail": "CSRF validation failed"}',
            status_code=status.HTTP_403_FORBIDDEN,
            media_type="application/json"
        )

    response = await call_next(request)
    return response
