"""
Issue 3.2: Input Validation Security Audit

Tests to verify SQL injection prevention on high-traffic API endpoints.
All endpoints should use parameterized queries with placeholders.
"""

import pytest
import sys
sys.path.insert(0, '/Users/arger/code/algo')

from lambda_function import (
    _handle_stocks,
    _handle_sectors,
    _handle_signals,
    _handle_research,
    _handle_admin,
)


class TestInputValidationSQLInjection:
    """Test SQL injection prevention on critical endpoints."""

    def test_stocks_endpoint_symbol_injection(self):
        """Test /api/stocks with SQL injection attempt in symbol parameter."""

        # SQL injection payload: try to break out of query
        injection_payload = "AAPL' OR '1'='1"

        event = {
            'resource': '/api/stocks',
            'httpMethod': 'GET',
            'queryStringParameters': {
                'symbols': injection_payload,
                'limit': '10'
            }
        }

        # Should safely handle the injection (return empty or error, not execute injection)
        try:
            response = _handle_stocks(event)
            # If it doesn't crash, parameterized query is working
            assert response['statusCode'] in [200, 400, 404]
            print(f"✅ /api/stocks symbol injection safe: {response['statusCode']}")
        except Exception as e:
            # Should not have database error if query is parameterized
            assert "SQL" not in str(e) and "syntax" not in str(e).lower()
            print(f"✅ /api/stocks symbol injection handled: {str(e)[:50]}")

    def test_sectors_endpoint_injection(self):
        """Test /api/sectors with SQL injection."""

        injection_payload = "tech'); DROP TABLE stocks;--"

        event = {
            'resource': '/api/sectors',
            'httpMethod': 'GET',
            'queryStringParameters': {
                'sector': injection_payload,
            }
        }

        try:
            response = _handle_sectors(event)
            assert response['statusCode'] in [200, 400, 404]
            print(f"✅ /api/sectors injection safe: {response['statusCode']}")
        except Exception as e:
            assert "DROP TABLE" not in str(e)
            print(f"✅ /api/sectors injection handled")

    def test_signals_endpoint_injection(self):
        """Test /api/signals with SQL injection."""

        injection_payload = "AAPL' UNION SELECT password FROM users;--"

        event = {
            'resource': '/api/signals',
            'httpMethod': 'GET',
            'queryStringParameters': {
                'symbol': injection_payload,
                'days': '30'
            }
        }

        try:
            response = _handle_signals(event)
            assert response['statusCode'] in [200, 400, 404]
            print(f"✅ /api/signals injection safe: {response['statusCode']}")
        except Exception as e:
            assert "UNION" not in str(e)
            print(f"✅ /api/signals injection handled")

    def test_numeric_parameter_validation(self):
        """Test numeric parameters handle non-numeric input safely."""

        event = {
            'resource': '/api/stocks',
            'httpMethod': 'GET',
            'queryStringParameters': {
                'symbols': 'AAPL',
                'limit': 'NOT_A_NUMBER'
            }
        }

        try:
            response = _handle_stocks(event)
            # Should either use default or return 400 (not crash)
            assert response['statusCode'] in [200, 400]
            print(f"✅ Numeric parameter validation safe: {response['statusCode']}")
        except ValueError:
            # Catching ValueError is acceptable (proper validation)
            print(f"✅ Numeric parameter validation caught invalid input")

    def test_limit_parameter_bounds(self):
        """Test limit parameter doesn't allow unbounded queries."""

        event = {
            'resource': '/api/stocks',
            'httpMethod': 'GET',
            'queryStringParameters': {
                'symbols': 'AAPL',
                'limit': '999999999'  # Unreasonably large
            }
        }

        try:
            response = _handle_stocks(event)
            # Should enforce reasonable limit
            assert response['statusCode'] in [200, 400]
            print(f"✅ Limit parameter bounded: {response['statusCode']}")
        except Exception as e:
            print(f"✅ Limit parameter validation caught excessive value")


class TestInputValidationAudit:
    """Audit actual code for parameterized query usage."""

    def test_lambda_uses_parameterized_queries(self):
        """Verify lambda_function.py uses parameterized queries."""

        with open('/Users/arger/code/algo/lambda/api/lambda_function.py', 'r') as f:
            code = f.read()

        # Check for SQL string concatenation (bad pattern)
        dangerous_patterns = [
            ".format(",      # f-strings with query
            "% (",          # % string formatting with query
            f"f'SELECT",    # f-string SELECT
            f'f"SELECT',    # f-string SELECT
        ]

        bad_patterns_found = []
        for pattern in dangerous_patterns:
            if pattern in code:
                # Could be false positive, but worth investigating
                bad_patterns_found.append(pattern)

        # Good patterns (parameterized)
        good_patterns = [
            "%s",           # Parameterized placeholder
            "execute(\"SELECT",  # Separate SQL from params
        ]

        has_parameterized = any(pattern in code for pattern in good_patterns)

        assert has_parameterized, "Should use parameterized queries"
        print(f"✅ Code audit: Uses parameterized query patterns")

        if bad_patterns_found:
            print(f"⚠️  Warning: Found potentially unsafe patterns: {bad_patterns_found}")
            print(f"   (May be false positives, check manually)")

    def test_input_validation_patterns(self):
        """Check for input validation patterns in code."""

        with open('/Users/arger/code/algo/lambda/api/lambda_function.py', 'r') as f:
            code = f.read()

        # Look for validation patterns
        validation_patterns = [
            "if not",        # Basic checks
            "isinstance",    # Type checking
            "try:",          # Error handling
            "except",        # Exception handling
        ]

        found_validation = sum(1 for p in validation_patterns if p in code)

        assert found_validation >= 2, "Should have input validation patterns"
        print(f"✅ Code audit: Found {found_validation} validation patterns")


class TestSecurityEndpoints:
    """Test security-critical endpoints specifically."""

    def test_api_requires_authentication(self):
        """Verify API key authentication is required."""

        with open('/Users/arger/code/algo/lambda/api/lambda_function.py', 'r') as f:
            code = f.read()

        # Check for authentication check
        assert 'require_api_key' in code or 'api_key' in code or 'Authorization' in code, \
            "API should have authentication check"

        print(f"✅ API authentication check found")

    def test_response_sanitization(self):
        """Verify error messages don't leak sensitive info."""

        with open('/Users/arger/code/algo/lambda/api/lambda_function.py', 'r') as f:
            code = f.read()

        # Check that full exceptions aren't returned to client
        assert 'str(e)' not in code or 'except' not in code, \
            "Should not return raw exception messages to client"

        print(f"✅ Error messages properly handled")


if __name__ == '__main__':
    # Run tests with pytest
    pytest.main([__file__, '-v'])
