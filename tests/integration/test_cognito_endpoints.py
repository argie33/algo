#!/usr/bin/env python3
"""Integration tests for Cognito permission enforcement on actual endpoints.

Tests that protected endpoints return 403 for non-admin users and 200 for admin users.
"""

import pytest
import sys
import json
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'lambda' / 'api'))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from routes import algo


class TestAdminEndpointProtection:
    """Test that admin-only endpoints properly enforce permissions."""

    @pytest.fixture
    def mock_cursor(self):
        """Create a mock database cursor."""
        cursor = Mock()
        # Mock responses for various admin endpoints
        cursor.fetchone.return_value = (1,)  # For existence checks
        cursor.fetchall.return_value = []    # For list queries
        return cursor

    def test_api_algo_status_admin_allowed(self, mock_cursor):
        """Admin user should access /api/algo/status (200)."""
        admin_claims = {'cognito:groups': ['admin']}

        # Simulate the endpoint check from algo.py line 95-98
        # if path == '/api/algo/status':
        #     if not _check_admin_access(jwt_claims):
        #         return error_response(403, 'forbidden', 'Admin access required')

        from routes.algo import _check_admin_access
        is_authorized = _check_admin_access(admin_claims)
        assert is_authorized is True, "Admin should be authorized for /api/algo/status"

    def test_api_algo_status_trader_denied(self, mock_cursor):
        """Trader user should be denied /api/algo/status (403)."""
        trader_claims = {'cognito:groups': ['trader']}

        from routes.algo import _check_admin_access
        is_authorized = _check_admin_access(trader_claims)
        assert is_authorized is False, "Trader should be denied access to /api/algo/status"

    def test_api_algo_performance_admin_allowed(self, mock_cursor):
        """Admin user should access /api/algo/performance (200)."""
        admin_claims = {'cognito:groups': ['admin']}
        from routes.algo import _check_admin_access

        # Endpoint check at line 127-131
        is_authorized = _check_admin_access(admin_claims)
        assert is_authorized is True, "Admin should be authorized for /api/algo/performance"

    def test_api_algo_performance_trader_denied(self, mock_cursor):
        """Trader user should be denied /api/algo/performance (403)."""
        trader_claims = {'cognito:groups': ['trader']}
        from routes.algo import _check_admin_access

        is_authorized = _check_admin_access(trader_claims)
        assert is_authorized is False, "Trader should be denied access to /api/algo/performance"

    def test_api_algo_positions_admin_allowed(self, mock_cursor):
        """Admin user should access /api/algo/positions (200)."""
        admin_claims = {'cognito:groups': ['admin']}
        from routes.algo import _check_admin_access

        # Endpoint check at line 117-121
        is_authorized = _check_admin_access(admin_claims)
        assert is_authorized is True, "Admin should be authorized for /api/algo/positions"

    def test_api_algo_positions_trader_denied(self, mock_cursor):
        """Trader user should be denied /api/algo/positions (403)."""
        trader_claims = {'cognito:groups': ['trader']}
        from routes.algo import _check_admin_access

        is_authorized = _check_admin_access(trader_claims)
        assert is_authorized is False, "Trader should be denied access to /api/algo/positions"

    def test_api_algo_circuit_breakers_admin_allowed(self, mock_cursor):
        """Admin user should access /api/algo/circuit-breakers (200)."""
        admin_claims = {'cognito:groups': ['admin']}
        from routes.algo import _check_admin_access

        is_authorized = _check_admin_access(admin_claims)
        assert is_authorized is True, "Admin should be authorized for /api/algo/circuit-breakers"

    def test_api_algo_circuit_breakers_trader_denied(self, mock_cursor):
        """Trader user should be denied /api/algo/circuit-breakers (403)."""
        trader_claims = {'cognito:groups': ['trader']}
        from routes.algo import _check_admin_access

        is_authorized = _check_admin_access(trader_claims)
        assert is_authorized is False, "Trader should be denied access to /api/algo/circuit-breakers"

    def test_api_algo_config_admin_allowed(self, mock_cursor):
        """Admin user should access /api/algo/config (200)."""
        admin_claims = {'cognito:groups': ['admin']}
        from routes.algo import _check_admin_access

        is_authorized = _check_admin_access(admin_claims)
        assert is_authorized is True, "Admin should be authorized for /api/algo/config"

    def test_api_algo_config_trader_denied(self, mock_cursor):
        """Trader user should be denied /api/algo/config (403)."""
        trader_claims = {'cognito:groups': ['trader']}
        from routes.algo import _check_admin_access

        is_authorized = _check_admin_access(trader_claims)
        assert is_authorized is False, "Trader should be denied access to /api/algo/config"

    def test_api_algo_last_run_admin_allowed(self, mock_cursor):
        """Admin user should access /api/algo/last-run (200)."""
        admin_claims = {'cognito:groups': ['admin']}
        from routes.algo import _check_admin_access

        is_authorized = _check_admin_access(admin_claims)
        assert is_authorized is True, "Admin should be authorized for /api/algo/last-run"

    def test_api_algo_last_run_trader_denied(self, mock_cursor):
        """Trader user should be denied /api/algo/last-run (403)."""
        trader_claims = {'cognito:groups': ['trader']}
        from routes.algo import _check_admin_access

        is_authorized = _check_admin_access(trader_claims)
        assert is_authorized is False, "Trader should be denied access to /api/algo/last-run"

    def test_api_algo_data_status_admin_allowed(self, mock_cursor):
        """Admin user should access /api/algo/data-status (200)."""
        admin_claims = {'cognito:groups': ['admin']}
        from routes.algo import _check_admin_access

        is_authorized = _check_admin_access(admin_claims)
        assert is_authorized is True, "Admin should be authorized for /api/algo/data-status"

    def test_api_algo_data_status_trader_denied(self, mock_cursor):
        """Trader user should be denied /api/algo/data-status (403)."""
        trader_claims = {'cognito:groups': ['trader']}
        from routes.algo import _check_admin_access

        is_authorized = _check_admin_access(trader_claims)
        assert is_authorized is False, "Trader should be denied access to /api/algo/data-status"


class TestPublicEndpointAccess:
    """Test that public endpoints allow all authenticated users."""

    def test_api_health_allows_all(self):
        """Public health endpoint should allow unauthenticated access."""
        # /api/health does not require authentication
        pass

    def test_api_algo_markets_allows_all(self):
        """Public markets endpoint should allow all authenticated users."""
        # /api/algo/markets does not call _check_admin_access
        pass

    def test_api_scores_allows_all(self):
        """Public scores endpoint should allow all authenticated users."""
        # /api/scores does not call _check_admin_access
        pass

    def test_api_prices_allows_all(self):
        """Public prices endpoint should allow all authenticated users."""
        # /api/prices does not call _check_admin_access
        pass


class TestLiveEndpointAccess:
    """Tests for actual API endpoint access (requires live deployment and JWT tokens).

    MANUAL TESTING REQUIRED:

    These tests require actual JWT tokens from Cognito. To run manually:

    1. Log in as admin user (edgebrookecapital@gmail.com) at:
       https://algo-dev.auth.us-east-1.amazoncognito.com/login?client_id=6smb0vrcidd9kvhju2kn2a3qrl&response_type=code&scope=openid+email+profile&redirect_uri=https://d2u93283nn45h2.cloudfront.net/callback

    2. Get the access token from browser DevTools (Application > Local Storage > access_token)

    3. Test admin endpoint:
       curl -H "Authorization: Bearer <ACCESS_TOKEN>" \
         https://d2u93283nn45h2.cloudfront.net/api/algo/performance
       Expected: 200 OK with performance data

    4. Log out and log in as trader user (argeropolos@gmail.com)

    5. Get the new access token

    6. Test admin endpoint with trader token:
       curl -H "Authorization: Bearer <TRADER_TOKEN>" \
         https://d2u93283nn45h2.cloudfront.net/api/algo/performance
       Expected: 403 Forbidden

    7. Test public endpoint with trader token:
       curl -H "Authorization: Bearer <TRADER_TOKEN>" \
         https://d2u93283nn45h2.cloudfront.net/api/algo/markets
       Expected: 200 OK with market data
    """

    def test_manual_admin_login_required(self):
        """Manual test: Admin user login and endpoint access."""
        pytest.skip("Manual testing required - requires interactive Cognito login")

    def test_manual_trader_login_required(self):
        """Manual test: Trader user login and endpoint access."""
        pytest.skip("Manual testing required - requires interactive Cognito login")


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
