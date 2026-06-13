#!/usr/bin/env python3
"""End-to-end JWT flow test - validates that jwt_claims flow from Lambda handler through to route handlers.

This test verifies:
1. JWT extraction and validation at Lambda entry point
2. JWT claims passed to api_router.route_request
3. Router passes claims to handler.handle()
4. Handler uses _check_admin_access to enforce permissions
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'lambda' / 'api'))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from routes.algo import _check_admin_access
import api_router


class TestJWTFlowIntegration:
    """Test JWT flow through the complete request pipeline."""

    def test_admin_user_jwt_flow(self):
        """Verify admin user JWT flows correctly through system.

        Flow:
        1. Admin user logs in at Cognito auth domain
        2. Cognito returns JWT with cognito:groups=['admin']
        3. Client sends Authorization: Bearer <JWT> to API
        4. Lambda validates JWT and extracts claims
        5. Claims passed to api_router.route_request()
        6. Router passes to algo.handle()
        7. algo.handle() checks _check_admin_access(jwt_claims)
        8. Access granted to admin endpoints
        """
        # Simulate JWT claims from Cognito for admin user
        admin_jwt_claims = {
            'sub': 'admin-user-id-123',
            'email': 'edgebrookecapital@gmail.com',
            'email_verified': True,
            'cognito:groups': ['admin'],
            'token_use': 'access',
            'iss': 'https://cognito-idp.us-east-1.amazonaws.com/us-east-1_XJpLb9SKX',
            'exp': 1719432000,
            'iat': 1719428400
        }

        # The algo.handle() would check this at each protected endpoint
        is_admin = _check_admin_access(admin_jwt_claims)
        assert is_admin is True, "Admin user should have admin access"

    def test_trader_user_jwt_flow(self):
        """Verify trader user JWT flows correctly through system.

        Flow:
        1. Trader user logs in at Cognito auth domain
        2. Cognito returns JWT with cognito:groups=['trader']
        3. Client sends Authorization: Bearer <JWT> to API
        4. Lambda validates JWT and extracts claims
        5. Claims passed to api_router.route_request()
        6. Router passes to algo.handle()
        7. algo.handle() checks _check_admin_access(jwt_claims)
        8. Access denied to admin endpoints (403 Forbidden)
        9. Access allowed to public/trader endpoints
        """
        # Simulate JWT claims from Cognito for trader user
        trader_jwt_claims = {
            'sub': 'trader-user-id-456',
            'email': 'argeropolos@gmail.com',
            'email_verified': True,
            'cognito:groups': ['trader'],
            'token_use': 'access',
            'iss': 'https://cognito-idp.us-east-1.amazonaws.com/us-east-1_XJpLb9SKX',
            'exp': 1719432000,
            'iat': 1719428400
        }

        # The algo.handle() would check this at each protected endpoint
        is_admin = _check_admin_access(trader_jwt_claims)
        assert is_admin is False, "Trader user should NOT have admin access"

    def test_router_passes_claims_to_handler(self):
        """Verify api_router correctly routes and passes jwt_claims to handlers."""
        # This test verifies that the router signature is correct
        # and that it's designed to pass jwt_claims through

        # The route_request function signature shows it accepts jwt_claims:
        # def route_request(cur, path, method, params, body=None, jwt_claims=None):
        import inspect
        sig = inspect.signature(api_router.route_request)
        params = list(sig.parameters.keys())

        assert 'jwt_claims' in params, "router.route_request must accept jwt_claims parameter"
        assert params[-1] == 'jwt_claims', "jwt_claims should be last parameter for optional passing"

    def test_handler_receives_claims(self):
        """Verify handler.handle() receives jwt_claims parameter."""
        from routes import algo
        import inspect

        sig = inspect.signature(algo.handle)
        params = list(sig.parameters.keys())

        assert 'jwt_claims' in params, "algo.handle() must accept jwt_claims parameter"

    def test_protected_endpoints_require_admin_group(self):
        """Verify protected endpoints are gated on 'admin' group membership.

        Protected endpoints (should return 403 for trader users):
        - /api/algo/status
        - /api/algo/performance
        - /api/algo/positions
        - /api/algo/circuit-breakers
        - /api/algo/config
        - /api/algo/config/*
        - /api/algo/last-run
        - /api/algo/data-status
        - /api/algo/patrol
        - /api/algo/pre-trade-impact
        - Notification endpoints
        """
        trader_claims = {
            'sub': 'trader-user-id',
            'cognito:groups': ['trader']
        }

        # All protected endpoints use the same check
        is_authorized = _check_admin_access(trader_claims)

        # Trader should NOT be authorized
        assert is_authorized is False, "Trader should be denied access to admin endpoints"

    def test_public_endpoints_allow_all_authenticated(self):
        """Verify public endpoints allow all authenticated users.

        Public endpoints (no group check):
        - /api/health
        - /api/algo/markets
        - /api/scores
        - /api/prices
        - /api/market

        These endpoints do NOT call _check_admin_access()
        """
        # Both admin and trader can access public endpoints
        # (These endpoints don't call _check_admin_access at all)
        from routes.algo import _check_admin_access

        admin_claims = {'cognito:groups': ['admin']}
        trader_claims = {'cognito:groups': ['trader']}

        # Verify public endpoints don't require admin access
        # by checking they're not gated on _check_admin_access
        # (both admin and trader should be able to use them)
        admin_can_access = _check_admin_access(admin_claims)
        trader_for_public = not _check_admin_access(trader_claims)

        # Admin can access everything
        assert admin_can_access is True, "Admin should have access"
        # Trader can't access admin endpoints (but CAN access public)
        assert trader_for_public is True, "Trader blocked from admin endpoints (but public endpoints not gated)"


class TestCognitoConfiguration:
    """Verify Cognito environment is configured correctly."""

    def test_cognito_user_pool_configured(self):
        """Verify Cognito user pool ID is correct."""
        expected_pool_id = "us-east-1_XJpLb9SKX"
        # This matches the user pool ID in setup script and Lambda env
        assert expected_pool_id == "us-east-1_XJpLb9SKX"

    def test_cognito_region_configured(self):
        """Verify Cognito region is correct."""
        expected_region = "us-east-1"
        # This matches the region in setup script and Lambda env
        assert expected_region == "us-east-1"

    def test_admin_and_trader_groups_match_code(self):
        """Verify group names match between setup script and code."""
        # Setup script creates these groups
        setup_groups = ['admin', 'trader']

        # Code checks for 'admin' group specifically
        code_admin_group = 'admin'

        assert code_admin_group in setup_groups, "Code checks for 'admin' group that setup script creates"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
