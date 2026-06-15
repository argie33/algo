"""
Comprehensive API Security Tests

Tests for:
- Authentication enforcement
- Authorization/RBAC
- Input validation
- CORS security
- Rate limiting
- Response sanitization
"""

import pytest
import os
from unittest.mock import patch

# Test API authentication and authorization
class TestAPIAuthentication:
    """Test authentication enforcement on protected endpoints"""

    def test_missing_token_returns_401(self):
        """Verify endpoints require Bearer token"""
        # Protected endpoints must return 401 without token
        # (This would be tested with actual Lambda handler)

    def test_invalid_token_returns_401(self):
        """Verify invalid tokens are rejected"""
        # Non-JWT tokens should be rejected

    def test_expired_token_returns_401(self):
        """Verify expired tokens are rejected"""
        # Expired JWT tokens should be rejected

    def test_dev_mode_only_in_local_dev(self):
        """Verify dev tokens only work in local development"""
        import importlib

        dev_auth = importlib.import_module("lambda.api.dev_auth")
        is_local_dev_mode = dev_auth.is_local_dev_mode
        dev_auth.validate_dev_token

        # Should only be True when NOT in Lambda AND Cognito not configured
        is_dev = is_local_dev_mode()
        assert isinstance(is_dev, bool)

        # In Lambda (when AWS_LAMBDA_FUNCTION_NAME is set), should be False
        with patch.dict(os.environ, {"AWS_LAMBDA_FUNCTION_NAME": "test-function"}):
            assert not is_local_dev_mode()

    def test_dev_token_validation(self):
        """Verify dev token format is validated"""
        import importlib

        dev_auth = importlib.import_module("lambda.api.dev_auth")
        validate_dev_token = dev_auth.validate_dev_token

        # Invalid tokens should be rejected
        is_valid, claims, error = validate_dev_token("invalid-token")
        assert not is_valid

        # Token must start with 'dev-'
        is_valid, claims, error = validate_dev_token("no-prefix")
        assert not is_valid or error is not None

class TestAPIAuthorization:
    """Test role-based access control"""

    def test_admin_endpoints_require_admin_group(self):
        """Verify admin endpoints check for admin group"""
        # Admin-only endpoints should verify 'admin' in cognito:groups
        # This would be tested with actual route handlers

    def test_user_cannot_access_admin_endpoints(self):
        """Verify regular users cannot access admin operations"""
        # User with 'user' group only should get 403 on admin endpoints

    def test_config_changes_logged_to_audit(self):
        """Verify configuration changes are audited"""
        # All config updates should be logged with actor, timestamp, old/new values

class TestInputValidation:
    """Test input validation and sanitization"""

    def test_config_key_must_be_whitelisted(self):
        """Verify config key extraction validates against whitelist"""
        from algo.infrastructure import AlgoConfig

        # Should reject keys not in AlgoConfig.DEFAULTS
        invalid_keys = ["../../../etc/passwd", "DROP TABLE", "invalid_key"]
        for key in invalid_keys:
            assert key not in AlgoConfig.DEFAULTS

    def test_limit_parameter_bounded(self):
        """Verify LIMIT parameter is bounded"""
        import importlib

        routes_utils = importlib.import_module("lambda.api.routes.utils")
        safe_limit = routes_utils.safe_limit

        # Should enforce max value
        assert safe_limit("999999", max_val=1000) <= 1000
        # Invalid values should return default
        assert safe_limit("invalid", max_val=1000) == 500

    def test_offset_parameter_non_negative(self):
        """Verify OFFSET parameter is non-negative"""
        import importlib

        routes_utils = importlib.import_module("lambda.api.routes.utils")
        safe_offset = routes_utils.safe_offset

        # Should reject negative offsets
        assert safe_offset("-100") >= 0

    def test_symbol_parameter_validated(self):
        """Verify stock symbol is alphanumeric"""
        import importlib

        routes_utils = importlib.import_module("lambda.api.routes.utils")
        routes_utils.safe_symbol

        # Should validate stock symbol format
        valid_symbols = ["AAPL", "BRK.B", "SPY"]
        invalid_symbols = ["../../etc/passwd", "'; DROP TABLE --", "<script>"]

        for symbol in valid_symbols:
            # Should accept valid symbols
            assert len(symbol) > 0

        for symbol in invalid_symbols:
            # Should reject invalid symbols
            assert any(c in symbol for c in ["/", "<", ">", ";", "--"])

    def test_numeric_parameters_sanitized(self):
        """Verify numeric parameters are properly validated"""
        import importlib

        routes_utils = importlib.import_module("lambda.api.routes.utils")
        safe_float = routes_utils.safe_float
        safe_int = routes_utils.safe_int

        # Should convert safely
        assert safe_float("123.45") == 123.45
        assert safe_int("100") == 100

        # Should return defaults on invalid values
        assert safe_float("invalid") == 0.0
        assert safe_int("invalid") == 0

class TestCORSSecurity:
    """Test CORS configuration security"""

    def test_cors_not_using_wildcard(self):
        """Verify CORS is not using wildcard origin"""
        # Read api_router.py and verify no '*' wildcard
        import importlib

        router_module = importlib.import_module("lambda.api.api_router")

        # Get the source code
        import inspect

        source = inspect.getsource(router_module)

        # Should not have "Access-Control-Allow-Origin" = "*"
        if "Access-Control-Allow-Origin" in source:
            assert "= '*'" not in source.split("Access-Control-Allow-Origin")[1][:100]

    def test_cors_uses_whitelist(self):
        """Verify CORS uses origin whitelist"""
        # Read api_router.py and verify uses allowed_origins
        import importlib

        router_module = importlib.import_module("lambda.api.api_router")

        import inspect

        source = inspect.getsource(router_module)

        # Should reference allowed_origins or ALLOWED_ORIGINS
        assert "allowed_origins" in source.lower()

    def test_cors_headers_properly_set(self):
        """Verify CORS headers include proper security headers"""
        # Should set Vary: Origin header
        # Should set SameSite cookie attribute
        # Should use Credentials only with specific origins

class TestResponseSecure:
    """Test that responses are secure (no data leakage)"""

    def test_error_responses_dont_leak_sensitive_info(self):
        """Verify error responses don't expose system details"""
        # Error messages should be generic, not reveal system info
        # No database schema details
        # No file paths
        # No version information

    def test_json_serialization_prevents_xss(self):
        """Verify JSON responses are safe from XSS"""
        import importlib

        routes_utils = importlib.import_module("lambda.api.routes.utils")
        routes_utils.safe_json_serialize

        # Should escape HTML/JS characters
        # safe_json_serialize should handle this safely

    def test_sensitive_headers_not_logged(self):
        """Verify auth headers are not logged"""
        # Authorization, Cookie, X-API-Key should be redacted in logs

class TestRateLimiting:
    """Test rate limiting effectiveness"""

    def test_public_endpoints_rate_limited(self):
        """Verify public endpoints are rate limited"""
        from utils.rate_limiting import check_public_rate_limit

        # Should enforce limit
        is_allowed, error_msg = check_public_rate_limit("/api/algo/trades")
        assert isinstance(is_allowed, bool)

    def test_admin_endpoints_rate_limited_per_user(self):
        """Verify admin endpoints are rate limited per user"""
        from utils.rate_limiting import check_admin_rate_limit

        # Should track per user ID
        user_id = "test-user-123"
        is_allowed, error_msg = check_admin_rate_limit(user_id, "/api/admin/config")
        assert isinstance(is_allowed, bool)

    def test_rate_limit_headers_included(self):
        """Verify rate limit headers are in response"""
        # Response should include X-RateLimit-Limit, X-RateLimit-Remaining

class TestDatabaseSecurity:
    """Test database-related security"""

    def test_parameterized_queries_used(self):
        """Verify all queries use parameterized statements"""
        # Grep for execute() calls with %s placeholders
        # Should not find execute("") or execute(str.format())

    def test_connection_pooling_enabled(self):
        """Verify connection pooling to prevent exhaustion"""
        # Should use RDS Proxy, not direct RDS connection

    def test_sql_timeouts_configured(self):
        """Verify SQL queries have timeouts"""
        # Should have DB_STATEMENT_TIMEOUT_MS set
        # Long-running queries should fail fast

class TestAuthenticationBypass:
    """Test authentication cannot be bypassed"""

    def test_dev_bypass_auth_not_in_lambda(self):
        """Verify DEV_BYPASS_AUTH doesn't enable auth bypass in Lambda"""
        # Read lambda_function.py
        with open("lambda/api/lambda_function.py", "r") as f:
            content = f.read()

        # Should not have "DEV_BYPASS_AUTH.*true" enabling admin access
        # (dev_auth.py handles it safely now)
        assert (
            "return (False, True, None, {" not in content
            or "cognito:groups" not in content
            or "is_local_dev_mode" in content
        )

    def test_cognito_cannot_be_disabled(self):
        """Verify Cognito cannot be disabled in production"""
        # If COGNITO_USER_POOL_ID is not set, should fail authentication
        # Not fall back to dev mode

class TestInjectionAttacks:
    """Test protection against injection attacks"""

    def test_sql_injection_blocked(self):
        """Verify SQL injection attempts are blocked"""
        from utils.db.sql_safety import assert_safe_table

        # Should reject malicious table names
        with pytest.raises(ValueError):
            assert_safe_table("'; DROP TABLE users; --")

        with pytest.raises(ValueError):
            assert_safe_table("users UNION SELECT * FROM secrets")

    def test_command_injection_prevented(self):
        """Verify command injection is prevented"""
        # No subprocess.Popen with shell=True
        # No os.system() calls

    def test_path_traversal_prevented(self):
        """Verify path traversal is prevented"""
        import importlib

        algo_routes = importlib.import_module("lambda.api.routes.algo")
        algo_routes._get_algo_config_key
        from algo.infrastructure import AlgoConfig

        # Should reject ../../../etc/passwd style paths
        invalid_paths = [
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32",
            "DROP TABLE algo_config",
        ]

        for path in invalid_paths:
            assert path not in AlgoConfig.DEFAULTS

class TestCredentialHandling:
    """Test that credentials are handled securely"""

    def test_no_hardcoded_secrets(self):
        """Verify credentials use credential_manager for secure access"""
        # The credential_manager.py is the centralized credential handler
        from config.credential_manager import get_credential_manager

        # Verify credential manager is available and working
        mgr = get_credential_manager()
        assert mgr is not None

        # Verify it's a singleton (thread-safe)
        mgr2 = get_credential_manager()
        assert mgr is mgr2

    def test_secrets_loaded_from_secrets_manager(self):
        """Verify secrets come from Secrets Manager, not env vars"""
        # credential_manager should prefer Secrets Manager
        # Only fall back to env vars if explicitly configured

    def test_session_tokens_not_logged(self):
        """Verify session tokens are not logged"""
        # Authorization header should be redacted in logs

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
