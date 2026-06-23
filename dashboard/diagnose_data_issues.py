#!/usr/bin/env python3
"""Diagnostic tool to identify data loading issues in AWS mode.

Run this to see which data sources are failing and why:
  python -m tools.dashboard.diagnose_data_issues

This will fetch all dashboard data and show:
- Which fetchers succeed/fail
- Critical fields that are missing
- Error messages for failures
- Data freshness issues
"""

import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from dashboard.error_boundary import get_error_message, has_error
from dashboard.fetchers import load_all

ET = ZoneInfo("America/New_York")


def diagnose() -> int:
    """Fetch all data and show diagnostic report."""
    print("=" * 80)
    print("DASHBOARD DATA DIAGNOSTIC REPORT")
    print(f"Time: {datetime.now(ET).strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print("=" * 80)
    print()

    # Fetch all data
    print("Fetching data from all endpoints...")
    data = load_all()

    # Analyze results
    successes = []
    failures = []
    critical_missing = []

    print()
    print("=" * 80)
    print("RESULTS")
    print("=" * 80)
    print()

    for fetcher_name, fetcher_data in sorted(data.items()):
        if has_error(fetcher_data):
            error_msg = get_error_message(fetcher_data)
            failures.append((fetcher_name, error_msg))
            status = "❌ FAILED"
        else:
            successes.append(fetcher_name)
            status = "✅ SUCCESS"

        print(f"[{status}] {fetcher_name:12} - ", end="")

        if has_error(fetcher_data):
            print(f"ERROR: {error_msg}")
        else:
            # Check critical fields
            critical_fields = {
                "port": ["total_portfolio_value", "total_cash", "position_count"],
                "perf": ["n", "w", "l"],
                "mkt": ["vix", "spy", "tier"],
                "run": ["run_id", "success"],
                "cfg": ["enabled", "mode"],
                "pos": ["items"],
                "health": ["items"],
            }

            fields_to_check = critical_fields.get(fetcher_name)
            if fields_to_check:
                missing = [f for f in fields_to_check if f not in fetcher_data or fetcher_data[f] is None]
                if missing:
                    critical_missing.append((fetcher_name, missing))
                    print(f"⚠ Missing critical: {missing}")
                else:
                    print("All critical fields present")
            else:
                print("Data fetched successfully")

    # Summary
    print()
    print("=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print()
    print(f"✅ Successes: {len(successes)}/{len(data)}")
    if successes:
        for name in successes[:5]:
            print(f"   - {name}")
        if len(successes) > 5:
            print(f"   ... and {len(successes) - 5} more")

    print()
    print(f"❌ Failures: {len(failures)}/{len(data)}")
    if failures:
        for name, msg in failures[:5]:
            print(f"   - {name}: {(msg or '')[:60]}")
        if len(failures) > 5:
            print(f"   ... and {len(failures) - 5} more")

    print()
    print(f"⚠ Critical Missing: {len(critical_missing)}")
    if critical_missing:
        for name, missing in critical_missing:
            print(f"   - {name}: {missing}")

    print()
    print("=" * 80)
    print("RECOMMENDATIONS")
    print("=" * 80)
    print()

    if len(failures) > 0:
        print("🔴 Data Loading Issues Detected:")
        print("   - Check API connectivity to AWS endpoints")
        print("   - Verify DASHBOARD_API_URL, COGNITO_USER_POOL_ID environment variables")
        print("   - Check AWS CloudWatch logs for API errors")
        print("   - Verify data loader jobs are running (check data freshness)")
        print()

    if len(critical_missing) > 0:
        print("🟡 Critical Field Missing:")
        print("   - Check that API is returning all required fields")
        print("   - Verify data loading pipeline hasn't crashed")
        print("   - Look for NULL values in database that should have data")
        print()

    if len(failures) == 0 and len(critical_missing) == 0:
        print("✅ All data sources healthy!")
        print("   - If dashboard shows issues, they're display/rendering bugs")
        print("   - Otherwise, all real data is available")
        print()

    return 0 if len(failures) == 0 and len(critical_missing) == 0 else 1


if __name__ == "__main__":
    sys.exit(diagnose())
