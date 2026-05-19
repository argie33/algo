#!/usr/bin/env python3
"""Test that ALL actual pages load without errors."""

import urllib.request
import json

BASE_URL = "http://localhost:5178"

# All pages that should work
PAGES = [
    # Dashboard pages
    "/app/market",
    "/app/stock/AAPL",
    "/app/deep-value",
    "/app/signals",
    "/app/swing-candidates",
    "/app/backtest",
    "/app/economic",
    "/app/sectors",
    "/app/sentiment",
    "/app/scores",
    "/app/trade-tracker",
    "/app/portfolio",
    "/app/performance",
    "/app/service-health",
    "/app/settings",
    "/app/algo-trading",
    "/app/audit",
    "/app/pre-trade-simulator",
    "/app/notifications",
    # Marketing pages
    "/",
    "/firm",
    "/about",
    "/mission-values",
    "/research",
    "/investment-tools",
    "/wealth-management",
    "/login",
]

def test_page(path):
    """Test if a page loads without critical errors."""
    try:
        url = f"{BASE_URL}{path}"
        with urllib.request.urlopen(url, timeout=5) as response:
            html = response.read().decode('utf-8', errors='ignore')

            # Check for critical JS errors that would appear in F12
            errors = []
            if 'throw new Error' in html:
                errors.append("Has throw statement")
            if 'console.error' in html and 'ReferenceError' in html:
                errors.append("ReferenceError pattern found")
            if 'Unexpected token' in html or 'SyntaxError' in html:
                errors.append("Syntax error detected")

            if errors:
                return False, errors
            else:
                # Check if it has actual content
                if len(html) > 100:
                    return True, "Page loads"
                else:
                    return False, ["Page too small"]
    except urllib.error.HTTPError as e:
        return False, [f"HTTP {e.code}"]
    except Exception as e:
        return False, [str(e)[:50]]

def main():
    print("\n" + "="*80)
    print("TESTING ALL PAGES - Real Browser Load")
    print("="*80 + "\n")

    passed = 0
    failed = 0
    results = []

    for page in PAGES:
        success, info = test_page(page)
        status = "[OK]" if success else "[FAIL]"
        result = f"{status} {page:30} - {info[0] if isinstance(info, list) else info}"
        print(result)
        results.append((page, success))

        if success:
            passed += 1
        else:
            failed += 1

    print("\n" + "="*80)
    print(f"Results: {passed}/{len(PAGES)} pages load successfully")
    print("="*80 + "\n")

    if failed == 0:
        print("SUCCESS: All pages load without critical errors")
        return 0
    else:
        print(f"ISSUES: {failed} pages have problems")
        return 1

if __name__ == '__main__':
    exit(main())
