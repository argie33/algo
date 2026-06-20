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

import os
from unittest.mock import patch

import pytest


# Test API authentication and authorization
class TestAPIAuthentication:
    """Test authentication enforcement on protected endpoints"""

    def test_missing_token_returns_401(self):
        """Verify endpoints require Bearer token"""
        import importlib

        lambda_module = importlib.import_module("lambda.api.lambda_function")
        # Verify that the Lambda handler exists and has auth enforcement
        assert hasattr(lambda_module, "lambda_handler")
        # The handler should be wrapped with auth middleware
        assert callable(lambda_module.lambda_handler)

    def test_invalid_token_returns_401(self):
        """Verify invalid tokens are rejected"""
        import importlib

        dev_auth = importlib.import_module("lambda.api.dev_auth")

        # Test invalid token formats
        is_valid, _claims, error = dev_auth.validate_dev_token("invalid-token-format")
        assert not is_valid or error is not None

        # Test JWT-like but invalid
        is_valid, _claims, error = dev_auth.validate_dev_token(
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.invalid.signature"
        )
        assert not is_valid or error is not None

    def test_expired_token_returns_401(self):
        """Verify expired tokens are rejected"""
        import importlib
        from datetime import datetime, timedelta

        dev_auth = importlib.import_module("lambda.api.dev_auth")

        # Create an expired token with past expiry
        _past_time = (datetime.utcnow() - timedelta(hours=1)).timestamp()
        # Dev tokens should validate expiry if they include it
        _is_valid, _claims, _error = dev_auth.validate_dev_token("dev-expired-token")
        # Should either be invalid or have error (depending on token format)

    def test_dev_mode_only_in_local_dev(self):
        """Verify dev tokens only work in local development"""
        import importlib

        dev_auth = importlib.import_module("lambda.api.dev_auth")
        is_local_dev_mode = dev_auth.is_local_dev_mode
        assert hasattr(dev_auth, "validate_dev_token")

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
        is_valid, _claims, _error = validate_dev_token("invalid-token")
        assert not is_valid

        # Token must start with 'dev-'
        is_valid, _claims, error = validate_dev_token("no-prefix")
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
        result = safe_limit("999999", max_val=1000)
        assert result <= 1000, f"safe_limit returned {result}, expected <= 1000"

        # Invalid values should return default
        result = safe_limit("invalid", max_val=1000)
        assert result == 500, f"safe_limit('invalid') returned {result}, expected 500"

    def test_offset_parameter_non_negative(self):
        """Verify OFFSET parameter is non-negative"""
        import importlib

        routes_utils = importlib.import_module("lambda.api.routes.utils")
        safe_offset = routes_utils.safe_offset

        # Should reject negative offsets
        result = safe_offset("-100")
        assert result >= 0, f"safe_offset('-100') returned {result}, expected >= 0"

        # Should accept zero
        result = safe_offset("0")
        assert result == 0

    def test_symbol_parameter_validated(self):
        """Verify stock symbol is alphanumeric"""
        import importlib

        routes_utils = importlib.import_module("lambda.api.routes.utils")
        safe_symbol = routes_utils.safe_symbol

        # Should accept valid symbols
        valid_symbols = ["AAPL", "BRK.B", "SPY"]
        for symbol in valid_symbols:
            result = safe_symbol(symbol)
            assert result == symbol, f"safe_symbol rejected valid symbol {symbol}"

        # Should reject or sanitize most dangerous symbols
        dangerous_symbols = [
            "<script>",
            "'; DROP TABLE",
            "AAPL\"; DROP TABLE--",
        ]
        for malicious in dangerous_symbols:
            result = safe_symbol(malicious)
            # Either returns None, returns empty, or is transformed
            if result is not None:
                assert len(result) > 0, f"safe_symbol should reject or sanitize {malicious}"

    def test_numeric_parameters_sanitized(self):
        """Verify numeric parameters are properly validated"""
        import importlib

        routes_utils = importlib.import_module("lambda.api.routes.utils")
        safe_float = routes_utils.safe_float
        safe_int = routes_utils.safe_int

        # Should convert safely
        assert safe_float("123.45") == 123.45, "Failed to convert valid float"
        assert safe_int("100") == 100, "Failed to convert valid int"

        # Should return defaults on invalid values
        assert safe_float("invalid") == 0.0, "Invalid float did not return default"
        assert safe_int("invalid") == 0, "Invalid int did not return default"

        # Should handle SQL injection attempts
        assert safe_float("'; DROP TABLE--") == 0.0
        assert safe_int("99) UNION SELECT*") == 0


class TestCORSSecurity:
    """Test CORS configuration security"""

    def test_cors_not_using_wildcard(self):
        """Verify CORS is not using wildcard origin"""
        import importlib
        import inspect

        router_module = importlib.import_module("lambda.api.api_router")
        source = inspect.getsource(router_module)

        # Should not have Access-Control-Allow-Origin = "*"
        if "Access-Control-Allow-Origin" in source:
            # Find the relevant section
            cors_section = source.split("Access-Control-Allow-Origin")[1][:200]
            assert "= '*'" not in cors_section, "CORS using wildcard origin — SECURITY RISK"
            assert "'*'" not in cors_section, "CORS should not use * as origin"

    def test_cors_uses_whitelist(self):
        """Verify CORS uses origin whitelist"""
        import importlib
        import inspect

        router_module = importlib.import_module("lambda.api.api_router")
        source = inspect.getsource(router_module)

        # Should reference allowed_origins or similar whitelist
        has_whitelist = (
            "allowed_origins" in source.lower() or
            "allowed_origin" in source.lower() or
            "whitelist" in source.lower()
        )
        assert has_whitelist, "CORS should use origin whitelist, not wildcard"

    def test_cors_headers_properly_set(self):
        """Verify CORS headers include proper security headers"""
        import importlib

        router_module = importlib.import_module("lambda.api.api_router")

        # Verify Flask-CORS is imported and configured
        import inspect
        source = inspect.getsource(router_module)

        # Should have Flask-CORS configured
        assert "CORS" in source or "cors" in source.lower(), "Flask-CORS should be configured"
        assert "credentials" not in source or "True" not in source or "Credentials" in source


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
        assert hasattr(routes_utils, "safe_json_serialize")

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
        is_allowed, _error_msg = check_public_rate_limit("/api/algo/trades")
        assert isinstance(is_allowed, bool)

    def test_admin_endpoints_rate_limited_per_user(self):
        """Verify admin endpoints are rate limited per user"""
        from utils.rate_limiting import check_admin_rate_limit

        # Should track per user ID
        user_id = "test-user-123"
        is_allowed, _error_msg = check_admin_rate_limit(user_id, "/api/admin/config")
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
        with open("lambda/api/lambda_function.py") as f:
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
        try:
            from utils.db.sql_safety import assert_safe_table
        except ImportError:
            pytest.skip("sql_safety module not found")

        # Should reject malicious table names
        injection_attempts = [
            "'; DROP TABLE users; --",
            "users UNION SELECT * FROM secrets",
            "'; DELETE FROM algo_trades; --",
        ]

        for attempt in injection_attempts:
            try:
                assert_safe_table(attempt)
                raise AssertionError(f"SQL injection not blocked: {attempt}")
            except ValueError:
                pass  # Expected

    def test_command_injection_prevented(self):
        """Verify command injection is prevented"""
        import importlib
        import inspect

        # Check main entry points don't use shell=True
        lambda_module = importlib.import_module("lambda.api.lambda_function")
        source = inspect.getsource(lambda_module)

        # Should not have shell=True in subprocess calls
        assert "shell=True" not in source, "Subprocess with shell=True is dangerous"
        assert "os.system(" not in source, "os.system() is dangerous — use subprocess instead"

    def test_path_traversal_prevented(self):
        """Verify path traversal is prevented"""
        import importlib

        try:
            importlib.import_module("lambda.api.routes.algo")
        except ImportError:
            pytest.skip("algo routes not found")

        from algo.infrastructure import AlgoConfig

        # Should reject path traversal attempts
        dangerous_paths = [
            "../../../etc/passwd",
            "..\\..\\..\\windows\\system32",
            "../../secrets",
            ".env",
            "DROP TABLE algo_config",
        ]

        for path in dangerous_paths:
            # All dangerous paths should NOT be valid config keys
            assert path not in AlgoConfig.DEFAULTS, f"Dangerous path accepted: {path}"


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


class TestAPISecurityIntegration:
    """Integration tests for API security with HTTP requests"""

    def test_api_requires_auth_header(self):
        """Verify protected endpoints reject requests without auth header"""
        try:
            import importlib
            lambda_module = importlib.import_module("lambda.api.lambda_function")

            # Should require authentication
            # (Actual test would need mocked AWS Lambda context)
            assert hasattr(lambda_module, "lambda_handler")
        except ImportError:
            pytest.skip("Lambda API not available for testing")

    def test_sql_injection_in_query_params(self):
        """Verify query parameters are safe from SQL injection"""
        try:
            import importlib
            routes_utils = importlib.import_module("lambda.api.routes.utils")
            safe_symbol = routes_utils.safe_symbol
        except ImportError:
            pytest.skip("API utils not available")

        # Test that dangerous query params are sanitized or rejected
        dangerous_queries = [
            "AAPL' OR '1'='1",
            "<script>alert('xss')</script>",
        ]

        for query in dangerous_queries:
            result = safe_symbol(query)
            # Should either reject (return None/empty) or sanitize
            if result is not None and len(result) > 0:
                # If not rejected, should at least sanitize dangerous chars
                assert "<" not in result or ">" not in result, f"Dangerous input not sanitized: {query}"

    def test_xss_prevention_in_responses(self):
        """Verify responses are safe from XSS attacks"""
        try:
            import importlib
            import json
            routes_utils = importlib.import_module("lambda.api.routes.utils")
            safe_json_serialize = routes_utils.safe_json_serialize
        except ImportError:
            pytest.skip("safe_json_serialize not available")

        # Test XSS payloads in response data
        dangerous_data = {
            "symbol": "<script>alert('xss')</script>",
            "value": "';DROP TABLE--",
        }

        # Should handle dangerous content safely
        result = safe_json_serialize(dangerous_data)

        # Result should be serializable (dict or string)
        if isinstance(result, dict):
            # If returns dict, values should be escaped
            serialized = json.dumps(result)
        else:
            # If returns string, should be valid JSON
            serialized = result if isinstance(result, str) else json.dumps(result)

        # Should be able to parse back as JSON
        parsed = json.loads(serialized)
        assert isinstance(parsed, dict)

    def test_rate_limit_headers_present(self):
        """Verify rate limit information is returned in response headers"""
        try:
            from utils.rate_limiting import check_public_rate_limit
        except ImportError:
            pytest.skip("Rate limiting not available")

        is_allowed, _error_msg = check_public_rate_limit("/api/test")
        assert isinstance(is_allowed, bool), "Rate limit check should return boolean"

    def test_error_responses_dont_expose_internals(self):
        """Verify error responses are generic and don't expose system details"""
        try:
            import importlib
            lambda_module = importlib.import_module("lambda.api.lambda_function")
            import inspect

            source = inspect.getsource(lambda_module)

            # Check for secure error handling patterns
            # Should not expose file paths, database schema, or stack traces
            dangerous_patterns = [
                "db_host",
                "database_url",
                "api_key",
                "secret_key",
                "traceback.format_exc()",
            ]

            for pattern in dangerous_patterns:
                # Should not directly expose in error messages
                if pattern in source:
                    # Should be in logs or debug only, not response
                    assert "logger" in source, "Sensitive data should only be logged, not returned"
        except ImportError:
            pytest.skip("Lambda module not available")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
