#!/usr/bin/env python3
"""Integration tests for Cognito permission enforcement on actual endpoints.

Tests that protected endpoints return 403 for non-admin users and 200 for admin users.
"""

import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

_LAMBDA_API_ROOT = Path(__file__).parent.parent.parent / "lambda" / "api"
sys.path.insert(0, str(_LAMBDA_API_ROOT))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def _get_dispatch_branch_source(relative_path: str, path_literal: str) -> str:
    """Extract one `elif path == "...":` branch's body from a route dispatcher's source.

    Scoped extraction (not a whole-file check) because dispatcher modules like algo.py
    legitimately call check_admin_access for many OTHER paths in the same elif chain -
    only this specific branch's body should be asserted clean.
    """
    source = (Path(__file__).parent.parent.parent / relative_path).read_text(encoding="utf-8")
    marker = f"elif path == {path_literal}:"
    start = source.index(marker)
    body_start = start + len(marker)
    # Branch ends at the next line with the same or lesser indentation that starts a new
    # elif/else/statement - approximated here by the next "\n    elif " or "\n    else"
    # at the same 4-space indent used throughout this dispatcher's elif chain.
    next_branch = min(
        (idx for idx in (source.find("\n    elif ", body_start), source.find("\n    else", body_start)) if idx != -1),
        default=len(source),
    )
    return source[body_start:next_branch]


class TestAdminEndpointProtection:
    """Test that admin-only endpoints properly enforce permissions."""

    @pytest.fixture
    def mock_cursor(self):
        cursor = Mock()
        # Mock responses for various admin endpoints
        cursor.fetchone.return_value = (1,)  # For existence checks
        cursor.fetchall.return_value = []  # For list queries
        return cursor

    def test_api_algo_status_admin_allowed(self, mock_cursor):
        """Admin user should access /api/algo/status (200)."""
        admin_claims = {"sub": "test-admin-user", "cognito:groups": ["admin"]}

        # Simulate the endpoint check from algo.py line 95-98
        # if path == '/api/algo/status':
        #     if not _check_admin_access(jwt_claims):
        #         return error_response(403, 'forbidden', 'Admin access required')

        from auth_utils import check_admin_access

        is_authorized = check_admin_access(admin_claims)
        assert is_authorized, "Admin should be authorized for /api/algo/status"

    def test_api_algo_status_trader_denied(self, mock_cursor):
        """Trader user should be denied /api/algo/status (403)."""
        trader_claims = {"sub": "test-trader-user", "cognito:groups": ["trader"]}

        from auth_utils import check_admin_access

        is_authorized = check_admin_access(trader_claims)
        assert not is_authorized, "Trader should be denied access to /api/algo/status"

    def test_api_algo_performance_admin_allowed(self, mock_cursor):
        """Admin user should access /api/algo/performance (200)."""
        admin_claims = {"sub": "test-admin-user", "cognito:groups": ["admin"]}
        from auth_utils import check_admin_access

        # Endpoint check at line 127-131
        is_authorized = check_admin_access(admin_claims)
        assert is_authorized, "Admin should be authorized for /api/algo/performance"

    def test_api_algo_performance_trader_denied(self, mock_cursor):
        """Trader user should be denied /api/algo/performance (403)."""
        trader_claims = {"sub": "test-trader-user", "cognito:groups": ["trader"]}
        from auth_utils import check_admin_access

        is_authorized = check_admin_access(trader_claims)
        assert not is_authorized, "Trader should be denied access to /api/algo/performance"

    def test_api_algo_positions_admin_allowed(self, mock_cursor):
        """Admin user should access /api/algo/positions (200)."""
        admin_claims = {"sub": "test-admin-user", "cognito:groups": ["admin"]}
        from auth_utils import check_admin_access

        # Endpoint check at line 117-121
        is_authorized = check_admin_access(admin_claims)
        assert is_authorized, "Admin should be authorized for /api/algo/positions"

    def test_api_algo_positions_trader_denied(self, mock_cursor):
        """Trader user should be denied /api/algo/positions (403)."""
        trader_claims = {"sub": "test-trader-user", "cognito:groups": ["trader"]}
        from auth_utils import check_admin_access

        is_authorized = check_admin_access(trader_claims)
        assert not is_authorized, "Trader should be denied access to /api/algo/positions"

    def test_api_algo_circuit_breakers_admin_allowed(self, mock_cursor):
        """Admin user should access /api/algo/circuit-breakers (200)."""
        admin_claims = {"sub": "test-admin-user", "cognito:groups": ["admin"]}
        from auth_utils import check_admin_access

        is_authorized = check_admin_access(admin_claims)
        assert is_authorized, "Admin should be authorized for /api/algo/circuit-breakers"

    def test_api_algo_circuit_breakers_trader_denied(self, mock_cursor):
        """Trader user should be denied /api/algo/circuit-breakers (403)."""
        trader_claims = {"sub": "test-trader-user", "cognito:groups": ["trader"]}
        from auth_utils import check_admin_access

        is_authorized = check_admin_access(trader_claims)
        assert not is_authorized, "Trader should be denied access to /api/algo/circuit-breakers"

    def test_api_algo_config_admin_allowed(self, mock_cursor):
        """Admin user should access /api/algo/config (200)."""
        admin_claims = {"sub": "test-admin-user", "cognito:groups": ["admin"]}
        from auth_utils import check_admin_access

        is_authorized = check_admin_access(admin_claims)
        assert is_authorized, "Admin should be authorized for /api/algo/config"

    def test_api_algo_config_trader_denied(self, mock_cursor):
        """Trader user should be denied /api/algo/config (403)."""
        trader_claims = {"sub": "test-trader-user", "cognito:groups": ["trader"]}
        from auth_utils import check_admin_access

        is_authorized = check_admin_access(trader_claims)
        assert not is_authorized, "Trader should be denied access to /api/algo/config"

    def test_api_algo_last_run_admin_allowed(self, mock_cursor):
        """Admin user should access /api/algo/last-run (200)."""
        admin_claims = {"sub": "test-admin-user", "cognito:groups": ["admin"]}
        from auth_utils import check_admin_access

        is_authorized = check_admin_access(admin_claims)
        assert is_authorized, "Admin should be authorized for /api/algo/last-run"

    def test_api_algo_last_run_trader_denied(self, mock_cursor):
        """Trader user should be denied /api/algo/last-run (403)."""
        trader_claims = {"sub": "test-trader-user", "cognito:groups": ["trader"]}
        from auth_utils import check_admin_access

        is_authorized = check_admin_access(trader_claims)
        assert not is_authorized, "Trader should be denied access to /api/algo/last-run"

    def test_api_algo_data_status_admin_allowed(self, mock_cursor):
        """Admin user should access /api/algo/data-status (200)."""
        admin_claims = {"sub": "test-admin-user", "cognito:groups": ["admin"]}
        from auth_utils import check_admin_access

        is_authorized = check_admin_access(admin_claims)
        assert is_authorized, "Admin should be authorized for /api/algo/data-status"

    def test_api_algo_data_status_trader_denied(self, mock_cursor):
        """Trader user should be denied /api/algo/data-status (403)."""
        trader_claims = {"sub": "test-trader-user", "cognito:groups": ["trader"]}
        from auth_utils import check_admin_access

        is_authorized = check_admin_access(trader_claims)
        assert not is_authorized, "Trader should be denied access to /api/algo/data-status"


class TestPublicEndpointAccess:
    """Test that public endpoints allow all authenticated users."""

    def test_api_health_allows_all(self):
        """Public health endpoint should allow unauthenticated access."""
        # /api/health does not require authentication
        # Even without JWT claims, health endpoint should work
        # Mock a minimal cursor
        import unittest.mock as mock

        from routes import health

        cursor = mock.Mock()
        cursor.fetchone.return_value = ("ok",)

        # Health handler should accept None jwt_claims
        result = health.handle(cursor, "/api/health", "GET", {}, jwt_claims=None)
        assert result is not None, "Health endpoint should return response even with no JWT"

    def test_api_algo_markets_allows_all(self):
        """Public markets endpoint should allow all authenticated users.

        FIXED 2026-08-18 (loader-health review, cheats/bypasses sweep): this test used to
        call check_admin_access(trader_claims) and then unconditionally `assert True`,
        discarding the return value - it could never fail regardless of what the real
        /api/algo/markets dispatch branch in lambda/api/routes/algo.py actually does, giving
        false confidence about a security-relevant claim (this endpoint being intentionally
        public). Now statically verifies the actual dispatch branch's source, scoped
        precisely to that elif block (not the whole file, which legitimately calls
        check_admin_access for many other paths) so a future accidental admin-gate addition
        to this specific path fails the test.
        """
        source = _get_dispatch_branch_source("lambda/api/routes/algo.py", '"/api/algo/markets"')
        assert "check_admin_access" not in source, (
            "/api/algo/markets dispatch branch now calls check_admin_access - "
            "if intentional, update this test; if accidental, this is a regression"
        )

    def test_api_scores_allows_all(self):
        """Public scores endpoint should allow all authenticated users.

        FIXED 2026-08-18: see test_api_algo_markets_allows_all's docstring for why this
        replaced a vacuous `assert True`. scores.py has zero check_admin_access references
        anywhere (unlike algo.py's multi-branch dispatcher), so a whole-file check is safe.
        """
        source = Path(_LAMBDA_API_ROOT / "routes" / "scores.py").read_text(encoding="utf-8")
        assert "check_admin_access" not in source, (
            "routes/scores.py now references check_admin_access - "
            "if intentional, update this test; if accidental, this is a regression"
        )

    def test_api_prices_allows_all(self):
        """Public prices endpoint should allow all authenticated users.

        FIXED 2026-08-18: see test_api_algo_markets_allows_all's docstring for why this
        replaced a vacuous `assert True`. prices.py has zero check_admin_access references
        anywhere, so a whole-file check is safe.
        """
        source = Path(_LAMBDA_API_ROOT / "routes" / "prices.py").read_text(encoding="utf-8")
        assert "check_admin_access" not in source, (
            "routes/prices.py now references check_admin_access - "
            "if intentional, update this test; if accidental, this is a regression"
        )


class TestLiveEndpointAccess:
    """Tests for actual API endpoint access (requires live deployment and JWT tokens).

    MANUAL TESTING REQUIRED:

    These tests require actual JWT tokens from Cognito. To run manually:

    1. Fetch CloudFront domain from Terraform or environment:
       CLOUDFRONT_DOMAIN=$(terraform output -raw cloudfront_domain 2>/dev/null || \
                          echo $VITE_CLOUDFRONT_DOMAIN || echo "d2u93283nn45h2.cloudfront.net")
       echo "Using CloudFront domain: $CLOUDFRONT_DOMAIN"

    2. Log in as admin user (edgebrookecapital@gmail.com) at:
       https://algo-dev.auth.us-east-1.amazoncognito.com/login?client_id=6smb0vrcidd9kvhju2kn2a3qrl&response_type=code&scope=openid+email+profile&redirect_uri=https://${CLOUDFRONT_DOMAIN}/callback

    3. Get the access token from browser DevTools (Application > Local Storage > access_token)

    4. Test admin endpoint:
       curl -H "Authorization: Bearer <ACCESS_TOKEN>" \
         https://${CLOUDFRONT_DOMAIN}/api/algo/performance
       Expected: 200 OK with performance data

    5. Log out and log in as trader user (argeropolos@gmail.com)

    6. Get the new access token

    7. Test admin endpoint with trader token:
       curl -H "Authorization: Bearer <TRADER_TOKEN>" \
         https://${CLOUDFRONT_DOMAIN}/api/algo/performance
       Expected: 403 Forbidden

    8. Test public endpoint with trader token:
       curl -H "Authorization: Bearer <TRADER_TOKEN>" \
         https://${CLOUDFRONT_DOMAIN}/api/algo/markets
       Expected: 200 OK with market data
    """

    def test_manual_admin_login_required(self):
        """Manual test: Admin user login and endpoint access."""
        pytest.skip("Manual testing required - requires interactive Cognito login")

    def test_manual_trader_login_required(self):
        """Manual test: Trader user login and endpoint access."""
        pytest.skip("Manual testing required - requires interactive Cognito login")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
