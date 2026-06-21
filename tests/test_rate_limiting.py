#!/usr/bin/env python3
"""Test rate limiting module functionality."""

import sys
from pathlib import Path


# Add project root to path
project_root = str(Path(__file__).parent.parent)
sys.path.insert(0, project_root)

from utils.rate_limiting import (
    ADMIN_RATE_LIMITS,
    PUBLIC_RATE_LIMITS,
    _admin_rate_limits,
    _public_rate_limits,
    check_admin_rate_limit,
    check_public_rate_limit,
)


def test_admin_rate_limit_basic():
    """Test admin rate limit with low threshold."""
    _admin_rate_limits.clear()

    user_id = "test_user_123"
    endpoint = "/api/admin/system-health"
    max_requests = 3
    window_seconds = 1

    # First 3 requests should be allowed
    for i in range(max_requests):
        allowed, msg = check_admin_rate_limit(user_id, endpoint, max_requests, window_seconds)
        assert allowed is True, f"Request {i + 1} should be allowed"

    # 4th request should be denied
    allowed, msg = check_admin_rate_limit(user_id, endpoint, max_requests, window_seconds)
    assert allowed is False, "Request 4 should be rate limited"
    assert "Rate limit exceeded" in msg

    print("[OK] Admin rate limit basic test passed")


def test_public_rate_limit_basic():
    """Test public rate limit with low threshold."""
    _public_rate_limits.clear()

    endpoint = "/api/algo/markets"
    max_requests = 2
    window_seconds = 1

    # First 2 requests should be allowed
    for i in range(max_requests):
        allowed, msg = check_public_rate_limit(endpoint, max_requests, window_seconds)
        assert allowed is True, f"Request {i + 1} should be allowed"

    # 3rd request should be denied
    allowed, msg = check_public_rate_limit(endpoint, max_requests, window_seconds)
    assert allowed is False, "Request 3 should be rate limited"
    assert "Rate limit exceeded" in msg

    print("[OK] Public rate limit basic test passed")


def test_admin_rate_limits_configured():
    """Test that admin endpoints have rate limit config."""
    critical_endpoints = [
        "/api/admin/system-health",
        "/api/admin/loader-status",
        "/api/algo/patrol",
        "/api/algo/pre-trade-impact",
    ]

    for endpoint in critical_endpoints:
        assert endpoint in ADMIN_RATE_LIMITS, f"Endpoint {endpoint} missing from ADMIN_RATE_LIMITS"
        config = ADMIN_RATE_LIMITS[endpoint]
        assert "max_requests" in config, f"{endpoint} missing max_requests"
        assert "window" in config, f"{endpoint} missing window"
        assert "description" in config, f"{endpoint} missing description"

    print("[OK] Admin rate limits configured correctly")


def test_public_rate_limits_configured():
    """Test that public endpoints have rate limit config."""
    critical_endpoints = [
        "/api/algo/markets",
        "/api/algo/swing-scores",
    ]

    for endpoint in critical_endpoints:
        assert endpoint in PUBLIC_RATE_LIMITS, f"Endpoint {endpoint} missing from PUBLIC_RATE_LIMITS"
        config = PUBLIC_RATE_LIMITS[endpoint]
        assert "max_requests" in config, f"{endpoint} missing max_requests"
        assert "window" in config, f"{endpoint} missing window"
        assert "description" in config, f"{endpoint} missing description"

    print("[OK] Public rate limits configured correctly")


def test_different_users_independent():
    """Test that rate limits are independent per user."""
    _admin_rate_limits.clear()

    endpoint = "/api/admin/system-health"

    # User 1: 3 requests
    for _i in range(3):
        allowed, _msg = check_admin_rate_limit("user_1", endpoint, max_requests=3, window_seconds=60)
        assert allowed is True

    # User 2: Should not be rate limited (independent bucket)
    allowed, _msg = check_admin_rate_limit("user_2", endpoint, max_requests=3, window_seconds=60)
    assert allowed is True, "User 2 should have independent rate limit"

    print("[OK] Per-user rate limits are independent")


if __name__ == "__main__":
    test_admin_rate_limit_basic()
    test_public_rate_limit_basic()
    test_admin_rate_limits_configured()
    test_public_rate_limits_configured()
    test_different_users_independent()
    print("\n[PASS] All rate limiting tests passed!")
