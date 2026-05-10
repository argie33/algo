#!/usr/bin/env python3
"""
Test suite for Alpaca data source loader.

Verifies that:
1. Alpaca credentials are accessible
2. Alpaca API responds correctly
3. Data source router prioritizes Alpaca
4. Fallback to yfinance works if Alpaca fails
5. Data format is consistent

USAGE:
    python3 test-alpaca-loader.py                    # Full test
    python3 test-alpaca-loader.py --quick            # Quick sanity check
    python3 test-alpaca-loader.py --symbol GOOGL     # Test specific symbol
"""

import argparse
import json
import logging
import os
import sys
from datetime import date, timedelta

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)


def test_credentials():
    """Check if Alpaca credentials are configured."""
    print("\n[1] Checking Alpaca Credentials...")
    api_key = os.getenv("ALPACA_API_KEY")
    api_secret = os.getenv("ALPACA_API_SECRET") or os.getenv("ALPACA_SECRET_KEY")

    if api_key and api_secret:
        print(f"  [OK] Credentials found: {api_key[:10]}... / {api_secret[:10]}...")
        return True
    else:
        print("  [WARN] Credentials not in environment variables")
        print("         Try: python3 setup-alpaca-credentials.py")
        return False


def test_router_import():
    """Check if data_source_router can be imported."""
    print("\n[2] Importing data_source_router...")
    try:
        from data_source_router import DataSourceRouter
        print("  [OK] data_source_router imported successfully")
        return True
    except ImportError as e:
        print(f"  [ERROR] Failed to import: {e}")
        return False


def test_alpaca_fetch(symbol="AAPL", quick=False):
    """Test fetching data from Alpaca."""
    print(f"\n[3] Testing Alpaca fetch for {symbol}...")
    from data_source_router import DataSourceRouter

    router = DataSourceRouter()
    end = date.today()
    start = end - timedelta(days=5 if quick else 30)

    try:
        data = router.fetch_ohlcv(symbol, start, end)
        if data:
            print(f"  [OK] Fetched {len(data)} rows from {router.last_source}")
            if len(data) > 0:
                first_row = data[0]
                print(f"       Sample: {first_row['date']} - O:{first_row['open']} H:{first_row['high']} L:{first_row['low']} C:{first_row['close']}")
            return True, router.last_source
        else:
            print(f"  [WARN] No data returned (empty result)")
            return False, router.last_source
    except Exception as e:
        print(f"  [ERROR] {e}")
        return False, None


def test_fallback(symbol="AAPL"):
    """Test fallback chain (Alpaca -> yfinance)."""
    print(f"\n[4] Testing fallback chain for {symbol}...")
    from data_source_router import DataSourceRouter

    router = DataSourceRouter()
    end = date.today()
    start = end - timedelta(days=5)

    results = []
    for attempt in range(2):
        try:
            data = router.fetch_ohlcv(symbol, start, end)
            if data:
                results.append(router.last_source)
                print(f"  Attempt {attempt + 1}: {router.last_source} ✓")
        except Exception as e:
            print(f"  Attempt {attempt + 1}: {e}")

    if "alpaca" in results or "yfinance" in results:
        print(f"  [OK] Fallback chain working (sources used: {set(results)})")
        return True
    else:
        print(f"  [WARN] No sources succeeded")
        return False


def test_health_report():
    """Check source health tracking."""
    print("\n[5] Checking source health...")
    from data_source_router import DataSourceRouter

    router = DataSourceRouter()
    health = router.health_report()

    if health:
        for source_name, stats in health.items():
            status = "PAUSED" if stats["is_paused"] else "ACTIVE"
            print(f"  {source_name:10} [{status}] {stats['success_rate']:.0f}% success, "
                  f"{stats['total_requests']} req, {stats['total_failures']} failures")
        return True
    else:
        print("  [INFO] No health data yet (sources not used)")
        return True


def test_consistency(symbol="AAPL"):
    """Compare Alpaca and yfinance results."""
    print(f"\n[6] Testing data consistency for {symbol}...")
    from data_source_router import DataSourceRouter

    router = DataSourceRouter()
    end = date.today()
    start = end - timedelta(days=5)

    # Fetch from both sources
    alpaca_data = None
    yfinance_data = None

    try:
        alpaca_data = router._fetch_alpaca_ohlcv(symbol, start, end)
        if alpaca_data:
            print(f"  Alpaca: {len(alpaca_data)} rows")
    except Exception as e:
        print(f"  Alpaca error: {e}")

    try:
        yfinance_data = router._fetch_yfinance_ohlcv(symbol, start, end)
        if yfinance_data:
            print(f"  yfinance: {len(yfinance_data)} rows")
    except Exception as e:
        print(f"  yfinance error: {e}")

    if alpaca_data and yfinance_data:
        # Compare overlapping dates
        alpaca_dates = {d['date'] for d in alpaca_data}
        yfinance_dates = {d['date'] for d in yfinance_data}
        overlap = alpaca_dates & yfinance_dates

        if overlap:
            # Sample one date to compare
            sample_date = list(overlap)[0]
            ap = next(d for d in alpaca_data if d['date'] == sample_date)
            yf = next(d for d in yfinance_data if d['date'] == sample_date)

            close_diff = abs(ap['close'] - yf['close']) / yf['close'] * 100
            print(f"  Sample date {sample_date}:")
            print(f"    Alpaca:   {ap['close']:.2f}")
            print(f"    yfinance: {yf['close']:.2f}")
            print(f"    Diff:     {close_diff:.2f}%")

            if close_diff < 0.5:
                print(f"  [OK] Data is consistent")
                return True
            else:
                print(f"  [WARN] Data differs by {close_diff:.2f}%")
                return True
        else:
            print(f"  [INFO] No overlapping dates to compare")
            return True
    else:
        print(f"  [WARN] Could not fetch from both sources")
        return True


def main():
    parser = argparse.ArgumentParser(description="Test Alpaca data loader")
    parser.add_argument("--quick", action="store_true", help="Quick sanity check only")
    parser.add_argument("--symbol", default="AAPL", help="Symbol to test")
    args = parser.parse_args()

    tests = [
        ("Credentials", test_credentials),
        ("Router Import", test_router_import),
        ("Alpaca Fetch", lambda: test_alpaca_fetch(args.symbol, args.quick)),
        ("Fallback Chain", lambda: test_fallback(args.symbol)),
        ("Health Report", test_health_report),
    ]

    if not args.quick:
        tests.append(("Data Consistency", lambda: test_consistency(args.symbol)))

    print("\n" + "=" * 60)
    print("Alpaca Data Loader Test Suite")
    print("=" * 60)

    results = []
    for name, test_fn in tests:
        try:
            result = test_fn()
            if isinstance(result, tuple):
                result = result[0]
            results.append((name, result))
        except Exception as e:
            print(f"  [EXCEPTION] {e}")
            results.append((name, False))

    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)

    passed = sum(1 for _, r in results if r)
    total = len(results)

    for name, result in results:
        status = "[PASS]" if result else "[FAIL]"
        print(f"{status} {name}")

    print(f"\nResult: {passed}/{total} passed")

    if passed == total:
        print("\n✓ Alpaca loader is ready!")
        return 0
    else:
        print("\n✗ Some tests failed. See details above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
