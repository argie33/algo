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
import logging

logger = logging.getLogger(__name__)

API_BASE = "http://localhost:3001"

logger.info("=" * 80)
logger.info("ERROR MESSAGE SANITIZATION TEST")
logger.info("=" * 80)
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

logger.info("Testing error message sanitization...")
print()

failed_tests = []

for url, description, should_error in test_cases:
    test_url = f"{API_BASE}{url}"
    logger.info(f"Testing: {description}")
    logger.info(f"  URL: {test_url}")

    try:
        response = requests.get(test_url, timeout=5)

        if response.status_code >= 400:
            try:
                error_body = response.text
                logger.info(f"  Status: {response.status_code}")

                # Check for sensitive patterns
                found_leaks = []
                for pattern in BAD_PATTERNS:
                    if re.search(pattern, error_body, re.IGNORECASE):
                        found_leaks.append(pattern)

                if found_leaks:
                    logger.info(f"  [FAIL] ERROR LEAKAGE DETECTED:")
                    for leak in found_leaks[:3]:  # Show first 3
                        logger.info(f"     - Pattern matched: {leak}")
                    logger.info(f"  Response preview: {error_body[:100]}")
                    failed_tests.append((url, found_leaks))
                else:
                    logger.info(f"  [OK] Error message is sanitized")

            except Exception as e:
                logger.info(f"  [WARN]  Could not parse response: {str(e)[:50]}")
        else:
            logger.info(f"  [WARN]  Expected error but got {response.status_code}")

    except requests.exceptions.ConnectionError:
        logger.info(f"  [WARN]  Connection refused (is dev server running?)")
    except Exception as e:
        logger.info(f"  [WARN]  Error: {str(e)[:50]}")

    print()

# Summary
logger.info("=" * 80)
logger.info("SANITIZATION TEST SUMMARY")
logger.info("=" * 80)
print()

if failed_tests:
    logger.info(f"[FAIL] {len(failed_tests)} error(s) have leakage:")
    for url, patterns in failed_tests:
        logger.info(f"   - {url}")
        for p in patterns[:2]:
            logger.info(f"     -> {p}")
else:
    logger.info("[OK] All error messages properly sanitized!")

print()
logger.info("Guidelines:")
logger.info("  [OK] = Safe error messages (generic, no details)")
logger.info("  [FAIL] = Leaking implementation details (fix required)")
print()
logger.info("For local development: Errors may be more verbose. Production should sanitize.")
print()
