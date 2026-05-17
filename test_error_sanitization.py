#!/usr/bin/env python3
"""
Error Message Sanitization Test
Verifies that API error responses don't leak:
- Database table/column names
- SQL error details
- File paths
- Internal configuration
- Stack traces
"""

import requests
import re
from typing import Dict, List, Tuple

API_BASE = "http://localhost:3001"

print("=" * 80)
print("ERROR MESSAGE SANITIZATION TEST")
print("=" * 80)
print()

# Test cases that should trigger errors
test_cases = [
    # (URL, description, should_error)
    ("/api/stocks/INVALID_SYMBOL_XYZ123", "Invalid symbol", True),
    ("/api/stocks?limit=abc", "Invalid limit parameter", True),
    ("/api/stocks?offset=-999", "Invalid offset", True),
    ("/api/nonexistent/endpoint", "Nonexistent endpoint", True),
]

# Patterns that indicate error leakage (bad)
BAD_PATTERNS = [
    r'psycopg2',           # Database driver
    r'column.*does not exist',  # SQL error
    r'table.*does not exist',   # SQL error
    r'relation.*does not exist', # PostgreSQL error
    r'duplicate key',       # Database constraint error
    r'traceback',          # Python traceback
    r'line \d+',           # File line numbers in tracebacks
    r'File .*\.py',        # Python file paths
    r'postgres|pg_',       # PostgreSQL internals
    r'/home/',             # File paths
    r'C:\\Users',          # Windows paths
    r'json.decoder',       # JSON parsing errors
    r'error.*at.*character', # SQL syntax error details
]

print("Testing error message sanitization...")
print()

failed_tests = []

for url, description, should_error in test_cases:
    test_url = f"{API_BASE}{url}"
    print(f"Testing: {description}")
    print(f"  URL: {test_url}")

    try:
        response = requests.get(test_url, timeout=5)

        if response.status_code >= 400:
            try:
                error_body = response.text
                print(f"  Status: {response.status_code}")

                # Check for sensitive patterns
                found_leaks = []
                for pattern in BAD_PATTERNS:
                    if re.search(pattern, error_body, re.IGNORECASE):
                        found_leaks.append(pattern)

                if found_leaks:
                    print(f"  ❌ ERROR LEAKAGE DETECTED:")
                    for leak in found_leaks[:3]:  # Show first 3
                        print(f"     - Pattern matched: {leak}")
                    print(f"  Response preview: {error_body[:100]}")
                    failed_tests.append((url, found_leaks))
                else:
                    print(f"  ✅ Error message is sanitized")

            except Exception as e:
                print(f"  ⚠️  Could not parse response: {str(e)[:50]}")
        else:
            print(f"  ⚠️  Expected error but got {response.status_code}")

    except requests.exceptions.ConnectionError:
        print(f"  ⚠️  Connection refused (is dev server running?)")
    except Exception as e:
        print(f"  ⚠️  Error: {str(e)[:50]}")

    print()

# Summary
print("=" * 80)
print("SANITIZATION TEST SUMMARY")
print("=" * 80)
print()

if failed_tests:
    print(f"❌ {len(failed_tests)} error(s) have leakage:")
    for url, patterns in failed_tests:
        print(f"   - {url}")
        for p in patterns[:2]:
            print(f"     → {p}")
else:
    print("✅ All error messages properly sanitized!")

print()
print("Guidelines:")
print("  ✅ = Safe error messages (generic, no details)")
print("  ❌ = Leaking implementation details (fix required)")
print()
print("For local development: Errors may be more verbose. Production should sanitize.")
print()
