"""
Tests for CSRF Protection
"""

import pytest
import hmac
import hashlib
from unittest.mock import MagicMock, AsyncMock

from api.csrf import (
    CSRFProtection,
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
    csrf_protection,
)


class TestCSRFProtection:
    """Test CSRF token generation and validation"""

    def test_generate_token(self):
        """Token generation should produce unique, secure tokens"""
        csrf = CSRFProtection("test_secret")

        token1 = csrf.generate_token()
        token2 = csrf.generate_token()

        # Tokens should be unique
        assert token1 != token2

        # Tokens should have reasonable entropy (URL-safe base64)
        assert len(token1) >= 32

    def test_sign_token(self):
        """Token signing should produce consistent signatures"""
        csrf = CSRFProtection("test_secret")
        token = "test_token_123"

        signed1 = csrf._sign_token(token)
        signed2 = csrf._sign_token(token)

        # Same input should produce same output
        assert signed1 == signed2

        # Format should be token.signature
        assert "." in signed1

    def test_verify_signature_valid(self):
        """Valid signature should be verified"""
        csrf = CSRFProtection("test_secret")
        token = "test_token_123"

        signed = csrf._sign_token(token)
        verified = csrf._verify_signature(signed)

        assert verified == token

    def test_verify_signature_invalid(self):
        """Invalid signature should fail verification"""
        csrf = CSRFProtection("test_secret")

        # Tampered signature
        tampered = "test_token_123.invalid_signature"
        assert csrf._verify_signature(tampered) is None

        # Different secret
        csrf2 = CSRFProtection("different_secret")
        signed = csrf2._sign_token("test_token_123")
        assert csrf._verify_signature(signed) is None

    def test_verify_malformed_token(self):
        """Malformed tokens should fail verification"""
        csrf = CSRFProtection("test_secret")

        assert csrf._verify_signature("no_separator") is None
        assert csrf._verify_signature("") is None
        assert csrf._verify_signature(None) is None

    def test_validate_csrf_valid(self):
        """Validation should pass with matching cookie and header"""
        csrf = CSRFProtection("test_secret")

        token = csrf.generate_token()
        signed_token = csrf._sign_token(token)

        # Mock request with matching tokens
        request = MagicMock()
        request.cookies = {CSRF_COOKIE_NAME: signed_token}
        request.headers = {CSRF_HEADER_NAME: token}

        assert csrf.validate_csrf(request) is True

    def test_validate_csrf_missing_cookie(self):
        """Validation should fail without cookie"""
        csrf = CSRFProtection("test_secret")

        request = MagicMock()
        request.cookies = {}
        request.headers = {CSRF_HEADER_NAME: "some_token"}

        assert csrf.validate_csrf(request) is False

    def test_validate_csrf_missing_header(self):
        """Validation should fail without header"""
        csrf = CSRFProtection("test_secret")

        token = csrf.generate_token()
        signed_token = csrf._sign_token(token)

        request = MagicMock()
        request.cookies = {CSRF_COOKIE_NAME: signed_token}
        request.headers = {}

        assert csrf.validate_csrf(request) is False

    def test_validate_csrf_token_mismatch(self):
        """Validation should fail with mismatched tokens"""
        csrf = CSRFProtection("test_secret")

        token = csrf.generate_token()
        signed_token = csrf._sign_token(token)

        request = MagicMock()
        request.cookies = {CSRF_COOKIE_NAME: signed_token}
        request.headers = {CSRF_HEADER_NAME: "different_token"}

        assert csrf.validate_csrf(request) is False

    def test_validate_csrf_tampered_signature(self):
        """Validation should fail with tampered cookie"""
        csrf = CSRFProtection("test_secret")

        token = csrf.generate_token()

        request = MagicMock()
        request.cookies = {CSRF_COOKIE_NAME: f"{token}.bad_signature"}
        request.headers = {CSRF_HEADER_NAME: token}

        assert csrf.validate_csrf(request) is False

    def test_set_csrf_cookie(self):
        """set_csrf_cookie should set proper cookie attributes"""
        csrf = CSRFProtection("test_secret")

        response = MagicMock()
        token = csrf.set_csrf_cookie(response)

        # Should call set_cookie with secure attributes
        response.set_cookie.assert_called_once()
        call_kwargs = response.set_cookie.call_args[1]

        assert call_kwargs["key"] == CSRF_COOKIE_NAME
        assert call_kwargs["httponly"] is True
        assert call_kwargs["secure"] is True
        assert call_kwargs["samesite"] == "strict"

        # Token should be valid
        assert len(token) >= 32


class TestCSRFMiddleware:
    """Test CSRF middleware behavior"""

    @pytest.mark.asyncio
    async def test_safe_methods_skipped(self):
        """GET, HEAD, OPTIONS should bypass CSRF validation"""
        from api.csrf import csrf_middleware

        for method in ["GET", "HEAD", "OPTIONS"]:
            request = MagicMock()
            request.method = method
            request.url.path = "/api/data"
            request.headers = {}

            call_next = AsyncMock(return_value="response")
            result = await csrf_middleware(request, call_next)

            # Should pass through without validation
            call_next.assert_called_once_with(request)

    @pytest.mark.asyncio
    async def test_bearer_token_skipped(self):
        """Requests with Bearer token should skip CSRF"""
        from api.csrf import csrf_middleware

        request = MagicMock()
        request.method = "POST"
        request.url.path = "/api/data"
        request.headers = {"Authorization": "Bearer abc123"}

        call_next = AsyncMock(return_value="response")
        result = await csrf_middleware(request, call_next)

        # Should pass through
        call_next.assert_called_once_with(request)

    @pytest.mark.asyncio
    async def test_health_endpoint_skipped(self):
        """Health/metrics endpoints should skip CSRF"""
        from api.csrf import csrf_middleware

        for path in ["/health", "/metrics", "/docs", "/openapi.json"]:
            request = MagicMock()
            request.method = "POST"
            request.url.path = path
            request.headers = {}

            call_next = AsyncMock(return_value="response")
            await csrf_middleware(request, call_next)

            call_next.assert_called()
            call_next.reset_mock()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
