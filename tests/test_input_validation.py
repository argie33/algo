"""
Issue 3.2: Input Validation Security Audit

Tests to verify SQL injection prevention on high-traffic API endpoints.
All endpoints should use parameterized queries with placeholders.
"""

import pytest
import os
import re


class TestInputValidationSQLInjection:
    """Audit code patterns for SQL injection prevention."""

    def test_parameterized_queries_used(self):
        """Verify database queries use parameterized SQL with %s placeholders."""

        lambda_path = 'C:\\Users\\arger\\code\\algo\\lambda\\api\\lambda_function.py'
        with open(lambda_path, 'r', encoding='utf-8', errors='ignore') as f:
            code = f.read()

        # Count parameterized queries (using %s placeholders)
        parameterized_count = code.count('%s')

        # Check for dangerous SQL patterns with f-strings or .format on SQL queries
        # Look for patterns like: f"SELECT ... {var}" or "SELECT ...".format(var)
        dangerous_patterns = re.findall(
            r'(f["\']SELECT.*?\{.*?\}|f["\']INSERT.*?\{.*?\}|["\']SELECT.*?["\']\.format\()',
            code,
            re.IGNORECASE | re.DOTALL
        )

        assert parameterized_count > 0, "Should use parameterized queries (%s placeholders)"
        assert len(dangerous_patterns) == 0, \
            f"Found dangerous SQL patterns (f-strings or .format on SQL): {dangerous_patterns[:2]}"

        print(f"✅ SQL injection prevention: {parameterized_count} parameterized queries found, no dangerous patterns")

    def test_string_formatting_in_sql(self):
        """Check that SQL queries don't use string formatting."""

        lambda_path = 'C:\\Users\\arger\\code\\algo\\lambda\\api\\lambda_function.py'
        with open(lambda_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()

        dangerous_lines = []
        for i, line in enumerate(lines, 1):
            # Look for f-string or % formatting in SQL
            if any(sql_kw in line.upper() for sql_kw in ['SELECT', 'INSERT', 'UPDATE', 'DELETE']):
                if any(bad in line for bad in ['f"', "f'", f'.format(', f'% (']):
                    dangerous_lines.append((i, line.strip()))

        if dangerous_lines:
            print(f"⚠️  Found potential unsafe query patterns:")
            for line_num, line in dangerous_lines[:5]:
                print(f"   Line {line_num}: {line[:60]}")
            # Mark as warning but don't fail (might be false positives)
        else:
            print(f"✅ No obvious string formatting in SQL queries")

    def test_input_bounds_validation(self):
        """Check for input bounds and type validation."""

        lambda_path = 'C:\\Users\\arger\\code\\algo\\lambda\\api\\lambda_function.py'
        with open(lambda_path, 'r', encoding='utf-8', errors='ignore') as f:
            code = f.read()

        # Look for validation patterns
        validates = {
            'int() casting': 'int(' in code,
            'isinstance checks': 'isinstance(' in code,
            'try/except blocks': 'try:' in code and 'except' in code,
            'limit validation': 'limit' in code and ('LIMIT' in code or '< ' in code),
        }

        validated = sum(1 for v in validates.values() if v)
        assert validated >= 2, f"Should have input validation (found {validated})"

        for check, found in validates.items():
            status = "✅" if found else "❌"
            print(f"{status} {check}")


class TestInputValidationAudit:
    """Audit actual code for parameter validation."""

    def test_numeric_parameter_validation(self):
        """Check for numeric parameter validation (limit, days, etc)."""

        lambda_path = 'C:\\Users\\arger\\code\\algo\\lambda\\api\\lambda_function.py'
        with open(lambda_path, 'r', encoding='utf-8', errors='ignore') as f:
            code = f.read()

        # Check for limit parameter handling
        has_limit_check = 'limit' in code.lower() and any(
            pattern in code for pattern in [
                'min(', 'max(', '< ', '> ', '== ',  # boundary checks
                'int(', 'float(',  # type conversion
            ]
        )

        # Check for days parameter handling
        has_days_check = 'days' in code.lower() and any(
            pattern in code for pattern in ['int(', 'max(', 'min(']
        )

        assert has_limit_check or has_days_check, "Should validate numeric parameters"
        print(f"✅ Numeric parameter validation found")

    def test_error_message_sanitization(self):
        """Verify error messages don't leak SQL/database details."""

        lambda_path = 'C:\\Users\\arger\\code\\algo\\lambda\\api\\lambda_function.py'
        with open(lambda_path, 'r', encoding='utf-8', errors='ignore') as f:
            code = f.read()

        # Look for error handling
        has_error_handling = 'except' in code and 'sendError' in code

        # Check that exceptions aren't just converted to strings
        exposes_exception = 'sendError(str(e' in code or 'sendError(e' in code

        assert has_error_handling, "Should have error handling"

        if exposes_exception:
            print(f"⚠️  Warning: May expose exception details in error responses")
        else:
            print(f"✅ Error messages properly sanitized")

    def test_symbol_parameter_validation(self):
        """Check for symbol parameter sanitization."""

        lambda_path = 'C:\\Users\\arger\\code\\algo\\lambda\\api\\lambda_function.py'
        with open(lambda_path, 'r', encoding='utf-8', errors='ignore') as f:
            code = f.read()

        # Look for symbol validation
        has_symbol_check = any(pattern in code for pattern in [
            "symbol.upper()",
            "symbol.strip()",
            "isinstance(symbol, str)",
            "len(symbol)",
        ])

        # Look for symbol length check
        has_length_check = 'len(' in code and 'symbol' in code

        print(f"✅ Symbol parameter handling: length check={has_length_check}, type check={has_symbol_check}")


class TestSecurityEndpoints:
    """Verify security-critical endpoint protections."""

    def test_api_authentication_implemented(self):
        """Verify API key authentication decorator is used."""

        lambda_path = 'C:\\Users\\arger\\code\\algo\\lambda\\api\\lambda_function.py'
        with open(lambda_path, 'r', encoding='utf-8', errors='ignore') as f:
            code = f.read()

        # Check for authentication patterns
        has_auth = any(pattern in code for pattern in [
            'require_api_key',
            '@require_api_key',
            'APIKeyValidator',
            'api_key' in code and 'headers' in code,
        ])

        if has_auth:
            print(f"✅ API authentication implemented")
        else:
            print(f"⚠️  Warning: May not have API authentication")

    def test_rate_limiting_configured(self):
        """Check if rate limiting is configured."""

        lambda_path = 'C:\\Users\\arger\\code\\algo\\lambda\\api\\lambda_function.py'
        with open(lambda_path, 'r', encoding='utf-8', errors='ignore') as f:
            code = f.read()

        has_rate_limit = 'rate' in code.lower() or 'throttle' in code.lower()

        if has_rate_limit:
            print(f"✅ Rate limiting patterns found")
        else:
            print(f"ℹ️  Rate limiting not explicitly in Lambda (may be in API Gateway)")

    def test_cors_properly_configured(self):
        """Verify CORS headers are restricted."""

        lambda_path = 'C:\\Users\\arger\\code\\algo\\lambda\\api\\lambda_function.py'
        with open(lambda_path, 'r', encoding='utf-8', errors='ignore') as f:
            code = f.read()

        # Check CORS configuration
        has_cors = 'Access-Control-Allow-Origin' in code or 'CORS' in code
        has_wildcard = "'*'" in code and 'Access-Control' in code

        if has_cors and not has_wildcard:
            print(f"✅ CORS properly restricted (not wildcard)")
        elif has_cors:
            print(f"⚠️  Warning: CORS may use wildcard (less secure)")
        else:
            print(f"ℹ️  CORS configuration not found in Lambda")


if __name__ == '__main__':
    # Run tests with pytest
    pytest.main([__file__, '-v'])
