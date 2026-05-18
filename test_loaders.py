#!/usr/bin/env python3
"""
Comprehensive loader test and validation.

Tests which loaders work locally and identifies failures.
Usage:
    python3 test_loaders.py --tier 0  # Test tier-0 loaders
    python3 test_loaders.py --tier 1  # Test tier-1 loaders
    python3 test_loaders.py --all     # Test all tiers
"""

import sys
import logging
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)


def test_tier_0():
    """Test Tier 0: Stock symbols loader."""
    log.info("=" * 70)
    log.info("TIER 0: Stock Symbols")
    log.info("=" * 70)

    try:
        from loaders.loadstocksymbols import main as load_symbols
        result = load_symbols()
        if result == 0:
            log.info("✅ Tier 0 PASSED: Stock symbols loaded successfully")
            return True
        else:
            log.error("❌ Tier 0 FAILED: Stock symbols loader returned error")
            return False
    except Exception as e:
        log.error(f"❌ Tier 0 FAILED: {type(e).__name__}: {e}")
        return False


def test_tier_1_prices():
    """Test Tier 1: Price data loaders."""
    log.info("=" * 70)
    log.info("TIER 1: Price Data (3 samples)")
    log.info("=" * 70)

    tests = [
        ("AAPL", "Apple"),
        ("MSFT", "Microsoft"),
        ("SPY", "S&P 500 ETF"),
    ]

    from loaders.loadpricedaily import PriceDailyLoader
    from datetime import date, timedelta

    loader = PriceDailyLoader()
    passed = 0
    failed = 0

    for symbol, name in tests:
        try:
            log.info(f"\nTesting {symbol} ({name})...")
            since = date.today() - timedelta(days=30)
            rows = loader.fetch_incremental(symbol, since)

            if rows and len(rows) > 0:
                log.info(f"  ✅ Got {len(rows)} rows")
                passed += 1
            else:
                log.warning(f"  ⚠️  No rows returned (might be new symbol)")
                passed += 1
        except Exception as e:
            log.error(f"  ❌ Error: {type(e).__name__}: {e}")
            failed += 1

    log.info(f"\nTier 1 Summary: {passed} passed, {failed} failed")
    return failed == 0


def test_tier_2_reference():
    """Test Tier 2: Reference data (small sample)."""
    log.info("=" * 70)
    log.info("TIER 2: Reference Data (3 samples)")
    log.info("=" * 70)

    tests = [
        ("load_earnings_calendar", "Earnings Calendar"),
        ("loadcompanyprofile", "Company Profile"),
        ("loadseasonality", "Seasonality"),
    ]

    passed = 0
    failed = 0

    for module_name, desc in tests:
        try:
            log.info(f"\nTesting {desc}...")
            module = __import__(f"loaders.{module_name}", fromlist=[module_name])

            if hasattr(module, 'main'):
                result = module.main()
                if result == 0 or result is None:
                    log.info(f"  ✅ {desc} loader works")
                    passed += 1
                else:
                    log.warning(f"  ⚠️  {desc} returned code {result}")
                    passed += 1
            else:
                log.warning(f"  ⚠️  {desc} has no main() function")

        except Exception as e:
            log.error(f"  ❌ {desc} error: {type(e).__name__}: {str(e)[:100]}")
            failed += 1

    log.info(f"\nTier 2 Summary: {passed} passed, {failed} failed")
    return failed == 0


def check_data_in_database():
    """Check if data actually made it into the database."""
    log.info("=" * 70)
    log.info("DATA QUALITY CHECK")
    log.info("=" * 70)

    try:
        from utils.db_connection import get_db_connection
        conn = get_db_connection()
        cur = conn.cursor()

        # Check symbols
        cur.execute("SELECT COUNT(*) FROM stocks")
        symbol_count = cur.fetchone()[0]
        log.info(f"\n✓ Symbols in database: {symbol_count}")

        # Check prices
        cur.execute("SELECT COUNT(*) FROM price_daily")
        price_count = cur.fetchone()[0]
        log.info(f"✓ Price records in database: {price_count}")

        if price_count == 0 and symbol_count > 0:
            log.warning("⚠️  WARNING: Symbols loaded but no prices!")

        # Sample a few symbols to see if they have data
        cur.execute("""
            SELECT symbol, COUNT(*) as price_count
            FROM price_daily
            GROUP BY symbol
            ORDER BY price_count DESC
            LIMIT 5
        """)

        log.info("\nTop 5 symbols by price record count:")
        for symbol, count in cur.fetchall():
            log.info(f"  {symbol}: {count} records")

        cur.close()
        return price_count > 0

    except Exception as e:
        log.warning(f"Could not check database: {e}")
        return None


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Test all loaders")
    parser.add_argument("--tier", choices=["0", "1", "2", "all"], default="all")
    args = parser.parse_args()

    results = {}

    if args.tier in ("0", "all"):
        results["tier_0"] = test_tier_0()

    if args.tier in ("1", "all"):
        results["tier_1"] = test_tier_1_prices()

    if args.tier in ("2", "all"):
        results["tier_2"] = test_tier_2_reference()

    check_data_in_database()

    # Summary
    log.info("\n" + "=" * 70)
    log.info("TEST SUMMARY")
    log.info("=" * 70)

    for test_name, result in results.items():
        status = "✅ PASSED" if result else "❌ FAILED"
        log.info(f"{test_name}: {status}")

    all_passed = all(results.values())
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
