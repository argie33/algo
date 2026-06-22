#!/usr/bin/env python3
"""Dashboard data diagnostic tool.

Runs all data fetchers and reports actual issues instead of showing placeholders.
Shows exactly which endpoints are failing and which fields are missing.

Usage:
  python -m tools.dashboard.diagnose_dashboard              # AWS mode (default)
  python -m tools.dashboard.diagnose_dashboard --local      # Local dev mode
  python -m tools.dashboard.diagnose_dashboard --verbose    # Show full responses
"""

import argparse
import json
from datetime import datetime
from zoneinfo import ZoneInfo

from tools.dashboard.api_data_layer import set_api_url
from tools.dashboard.error_boundary import get_error_message, has_error
from tools.dashboard.fetchers import FETCHER_METADATA, load_all

ET = ZoneInfo("America/New_York")


def diagnose_fetchers():
    """Load all data and show detailed diagnostic report."""
    print("\n" + "=" * 80)
    print("Dashboard Data Diagnostic Report")
    print(f"Generated: {datetime.now(ET).strftime('%Y-%m-%d %I:%M %p ET')}")
    print("=" * 80 + "\n")

    # Load all data
    print("Loading data from all endpoints...")
    try:
        data = load_all()
    except Exception as e:
        print(f"CRITICAL: Failed to load data: {e}")
        return

    print(f"Loaded {len(data)} endpoints\n")

    # Categorize results
    success = {}
    errors = {}
    stale = {}
    missing_fields = {}

    for key, result in data.items():
        if not isinstance(result, dict):
            errors[key] = f"Non-dict response: {type(result)}"
            continue

        # Check for error
        if has_error(result):
            error_msg = get_error_message(result)
            if result.get("_data_stale"):
                stale[key] = error_msg
            else:
                errors[key] = error_msg
        else:
            # Check for missing fields (fields that are None)
            none_fields = [k for k, v in result.items() if v is None and not k.startswith("_")]
            if none_fields:
                missing_fields[key] = none_fields
            success[key] = result

    # Print summary
    print("SUMMARY")
    print(f"  ✓ Success:        {len(success)}")
    print(f"  ⚠ Stale:          {len(stale)}")
    print(f"  ✗ Errors:         {len(errors)}")
    print(f"  ⚡ Missing fields: {len(missing_fields)}")
    print()

    # Show successful fetchers
    if success:
        print("=" * 80)
        print("SUCCESSFUL FETCHERS (✓)")
        print("=" * 80)
        for key in sorted(success.keys()):
            meta = FETCHER_METADATA.get(key)
            endpoint = meta.get("endpoint", "?")
            desc = meta.get("desc", "")
            result = success[key]
            field_count = len([k for k in result.keys() if not k.startswith("_")])
            print(f"\n  {key:12} {endpoint:40} ({field_count} fields)")
            if desc:
                print(f"  {' ' * 12} {desc}")
        print()

    # Show stale data (yellow warning)
    if stale:
        print("=" * 80)
        print("STALE DATA (⚠ - Data too old)")
        print("=" * 80)
        for key, error_msg in sorted(stale.items()):
            meta = FETCHER_METADATA.get(key)
            endpoint = meta.get("endpoint", "?")
            desc = meta.get("desc", "")
            print(f"\n  {key:12} {endpoint:40}")
            if desc:
                print(f"  {' ' * 12} {desc}")
            print(f"  {' ' * 12} {error_msg}")
        print()

    # Show errors (red)
    if errors:
        print("=" * 80)
        print("FAILED FETCHERS (✗ - Cannot retrieve data)")
        print("=" * 80)
        for key, error_msg in sorted(errors.items()):
            meta = FETCHER_METADATA.get(key)
            endpoint = meta.get("endpoint", "?")
            desc = meta.get("desc", "")
            print(f"\n  {key:12} {endpoint:40}")
            if desc:
                print(f"  {' ' * 12} {desc}")
            print(f"  {' ' * 12} Error: {error_msg}")
        print()

    # Show missing fields (data returned but some fields are None)
    if missing_fields:
        print("=" * 80)
        print("PARTIAL DATA (⚡ - Some fields missing)")
        print("=" * 80)
        for key, fields in sorted(missing_fields.items()):
            meta = FETCHER_METADATA.get(key)
            endpoint = meta.get("endpoint", "?")
            print(f"\n  {key:12} {endpoint:40}")
            print(f"  {' ' * 12} Missing fields: {', '.join(fields)}")
        print()

    # Show recommendations
    print("=" * 80)
    print("RECOMMENDATIONS")
    print("=" * 80)
    if errors:
        print(f"\n1. FIX {len(errors)} BROKEN ENDPOINTS:")
        for key in sorted(errors.keys()):
            meta = FETCHER_METADATA.get(key)
            endpoint = meta.get("endpoint", "?")
            print(f"   - {key:12} {endpoint}")
    if stale:
        print(f"\n2. UPDATE {len(stale)} STALE DATA SOURCES:")
        print("   (Data loaders not running or data too old)")
        for key in sorted(stale.keys()):
            meta = FETCHER_METADATA.get(key)
            endpoint = meta.get("endpoint", "?")
            print(f"   - {key:12} {endpoint}")
    if missing_fields:
        print(f"\n3. INVESTIGATE {len(missing_fields)} PARTIAL RESPONSES:")
        print("   (Why are these fields None in the API response?)")
        for key in sorted(missing_fields.keys()):
            print(f"   - {key:12} missing: {', '.join(missing_fields[key][:3])}")

    print("\n" + "=" * 80)
    print("Run with --verbose to see full JSON responses")
    print("=" * 80 + "\n")


def diagnose_fetchers_verbose():
    """Load all data and show detailed response data."""
    print("\n" + "=" * 80)
    print("Dashboard Data Diagnostic Report (VERBOSE)")
    print(f"Generated: {datetime.now(ET).strftime('%Y-%m-%d %I:%M %p ET')}")
    print("=" * 80 + "\n")

    # Load all data
    print("Loading data from all endpoints...")
    try:
        data = load_all()
    except Exception as e:
        print(f"CRITICAL: Failed to load data: {e}")
        return

    print()
    for key in sorted(data.keys()):
        result = data[key]
        meta = FETCHER_METADATA.get(key)
        endpoint = meta.get("endpoint", "?")

        # Determine status
        if has_error(result):
            status = "ERROR"
        elif isinstance(result, dict) and result.get("_data_stale"):
            status = "STALE"
        else:
            status = "OK"

        print(f"\n{status:6} {key:12} {endpoint}")
        print("-" * 80)

        # Show response (pretty-printed JSON)
        if isinstance(result, dict):
            # Remove large fields for readability
            display = dict(result)
            for large_field in ["equity_vals", "recent_rets", "items"]:
                if large_field in display:
                    items_len = len(display[large_field]) if isinstance(display[large_field], list) else 0
                    display[large_field] = f"[{items_len} items]"
            try:
                output = json.dumps(display, indent=2, default=str)
                print(output)
            except Exception as e:
                print(f"Could not serialize: {e}")
        else:
            print(f"Non-dict: {type(result)}")

    print("\n" + "=" * 80)


def main():
    parser = argparse.ArgumentParser(
        description="Diagnose dashboard data issues",
        epilog=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--local",
        action="store_true",
        help="Use local API (localhost:3001) instead of AWS",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show full response data (JSON dump)",
    )
    args = parser.parse_args()

    if args.local:
        print("Using local API (localhost:3001)")
        set_api_url("http://localhost:3001")
    else:
        print("Using AWS API")

    if args.verbose:
        diagnose_fetchers_verbose()
    else:
        diagnose_fetchers()


if __name__ == "__main__":
    main()
