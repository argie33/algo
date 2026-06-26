#!/usr/bin/env python3
"""Unit tests for Cognito auth header generation and validation.

Tests that:
- Authorization headers are properly formatted
- Expired tokens are not returned
- Failed token refresh is handled gracefully
- Token format is validated before returning
"""

import base64
import json
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dashboard.cognito_auth import CognitoAuth


def create_jwt(exp: int, sub: str = "user-123") -> str:
    """Create a properly encoded JWT for testing."""
    header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256"}).encode()).decode().rstrip("=")
    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp, "sub": sub}).encode()).decode().rstrip("=")
    signature = base64.urlsafe_b64encode(b"test-signature").decode().rstrip("=")
    return f"{header}.{payload}.{signature}"


class TestAuthorizationHeaderValidation:
    """Test authorization header generation and validation."""

    def test_no_token_raises_error(self):
        """Should raise RuntimeError when no access token exists (fail-fast)."""
        auth = CognitoAuth("pool-123", "client-456")
        with pytest.raises(RuntimeError, match="no access token"):
            auth.get_authorization_header()

    def test_valid_token_returns_bearer_header(self):
        """Should return Bearer token when token is valid and not expired."""
        auth = CognitoAuth("pool-123", "client-456")
        # Create a mock JWT token (not expired)
        future_exp = int(time.time()) + 3600
        auth.access_token = create_jwt(future_exp)
        auth.token_expires_at = future_exp

        header = auth.get_authorization_header()
        assert "Authorization" in header
        assert header["Authorization"].startswith("Bearer ")
        assert auth.access_token in header["Authorization"]

    def test_expired_token_with_no_refresh_raises_error(self):
        """Should raise error when token is expired and no refresh token (fail-closed)."""
        auth = CognitoAuth("pool-123", "client-456")
        # Create an expired token
        past_exp = int(time.time()) - 3600
        auth.access_token = create_jwt(past_exp)
        auth.token_expires_at = past_exp
        auth.refresh_token = None

        with pytest.raises(RuntimeError, match="Token expired and no refresh token"):
            auth.get_authorization_header()

    def test_expired_token_with_failed_refresh_raises_error(self):
        """Should raise error when token refresh fails (fail-closed)."""
        auth = CognitoAuth("pool-123", "client-456")
        # Create an expired token
        past_exp = int(time.time()) - 3600
        auth.access_token = create_jwt(past_exp)
        auth.token_expires_at = past_exp
        auth.refresh_token = "refresh-token-123"

        # Mock refresh_access_token to return False (failure)
        with patch.object(auth, "refresh_access_token", return_value=False):
            with pytest.raises(RuntimeError, match="Token refresh failed"):
                auth.get_authorization_header()

    def test_expired_token_with_successful_refresh_returns_new_token(self):
        """Should return new token when refresh succeeds."""
        auth = CognitoAuth("pool-123", "client-456")
        # Create an expired token
        past_exp = int(time.time()) - 3600
        old_token = create_jwt(past_exp)
        auth.access_token = old_token
        auth.token_expires_at = past_exp
        auth.refresh_token = "refresh-token-123"

        # New token after refresh
        future_exp = int(time.time()) + 3600
        new_token = create_jwt(future_exp)

        def mock_refresh(self):
            self.access_token = new_token
            self.token_expires_at = future_exp
            return True

        with patch.object(CognitoAuth, "refresh_access_token", mock_refresh):
            header = auth.get_authorization_header()
            # Should return the new refreshed token, not the old expired one
            assert "Authorization" in header
            assert new_token in header["Authorization"]
            assert old_token not in header["Authorization"]

    def test_malformed_token_raises_error(self):
        """Should raise error when token is not a valid JWT (fail-closed)."""
        auth = CognitoAuth("pool-123", "client-456")
        # Malformed token (not 3 dot-separated parts)
        auth.access_token = "not-a-valid-jwt"
        auth.token_expires_at = int(time.time()) + 3600

        with pytest.raises(RuntimeError, match="token is not a valid JWT"):
            auth.get_authorization_header()

    def test_jwt_with_missing_parts_raises_error(self):
        """Should raise error when JWT has missing parts (fail-closed)."""
        auth = CognitoAuth("pool-123", "client-456")
        # JWT with only 2 parts
        auth.access_token = "header.payload"
        auth.token_expires_at = int(time.time()) + 3600

        with pytest.raises(RuntimeError, match="token is not a valid JWT"):
            auth.get_authorization_header()

    def test_jwt_with_empty_parts_raises_error(self):
        """Should raise error when JWT has empty parts (fail-closed)."""
        auth = CognitoAuth("pool-123", "client-456")
        # JWT with empty part
        auth.access_token = "header..signature"
        auth.token_expires_at = int(time.time()) + 3600

        with pytest.raises(RuntimeError, match="token is not a valid JWT"):
            auth.get_authorization_header()

    def test_jwt_format_validation(self):
        """Test _is_valid_jwt method with proper JWT structure and claims."""
        auth = CognitoAuth("pool-123", "client-456")

        # Valid JWT format with required claims - create properly encoded parts
        header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256"}).encode()).decode().rstrip("=")
        payload = (
            base64.urlsafe_b64encode(json.dumps({"exp": int(time.time()) + 3600, "sub": "user-123"}).encode())
            .decode()
            .rstrip("=")
        )
        signature = base64.urlsafe_b64encode(b"test-signature").decode().rstrip("=")
        valid_jwt = f"{header}.{payload}.{signature}"
        assert auth._is_valid_jwt(valid_jwt) is True

        # Invalid formats
        assert auth._is_valid_jwt("not-a-jwt") is False
        assert auth._is_valid_jwt("header.payload") is False
        assert auth._is_valid_jwt("header..signature") is False
        assert auth._is_valid_jwt("") is False
        assert auth._is_valid_jwt("...") is False

        # Valid structure but missing required claims
        missing_claims_payload = base64.urlsafe_b64encode(json.dumps({"data": "value"}).encode()).decode().rstrip("=")
        missing_claims_jwt = f"{header}.{missing_claims_payload}.{signature}"
        assert auth._is_valid_jwt(missing_claims_jwt) is False

        # Valid structure but invalid base64 payload
        assert auth._is_valid_jwt("header.!!!invalid-base64!!!.signature") is False


class TestTokenExpiryBuffer:
    """Test token expiry buffer (5 minute buffer before actual expiry)."""

    def test_token_expiry_5min_buffer(self):
        """Token should be considered expired 5 minutes before actual expiry."""
        auth = CognitoAuth("pool-123", "client-456")
        now = time.time()
        # Token expires in 4 minutes (240 seconds) - should be considered expired
        auth.token_expires_at = now + 240
        assert auth.is_token_expired() is True

        # Token expires in 6 minutes (360 seconds) - should NOT be considered expired
        auth.token_expires_at = now + 360
        assert auth.is_token_expired() is False

    def test_expired_token_refresh_on_header_call(self):
        """Should attempt refresh when getting header with token about to expire."""
        auth = CognitoAuth("pool-123", "client-456")
        now = time.time()
        # Token expires in 4 minutes (within 5-minute buffer)
        auth.token_expires_at = now + 240
        auth.refresh_token = "refresh-token-123"

        future_exp = int(now + 3600)
        new_token = create_jwt(future_exp)
        auth.access_token = "old-token"

        refresh_called = []

        def mock_refresh(self):
            refresh_called.append(True)
            self.access_token = new_token
            self.token_expires_at = future_exp
            return True

        with patch.object(CognitoAuth, "refresh_access_token", mock_refresh):
            header = auth.get_authorization_header()
            # Should have called refresh because token is about to expire
            assert len(refresh_called) > 0
            assert "Authorization" in header


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
