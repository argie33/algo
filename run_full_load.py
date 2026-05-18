#!/usr/bin/env python3
"""
Full end-to-end data load - LOCAL and AWS.

Runs all tiers of loaders in sequence:
  Tier 0: Stock symbols (prerequisite for all others)
  Tier 1: Price data (daily, weekly, monthly, aggregates)
  Tier 2: Reference data (financials, earnings, economic, sentiment)
  Tier 3: Computed metrics (technical indicators, scores)

Usage:
    python3 run_full_load.py --local          # Load to local PostgreSQL
    python3 run_full_load.py --aws            # Load to AWS RDS (requires credentials)
    python3 run_full_load.py --validate       # Validate data in database
    python3 run_full_load.py --all            # Full load + validation
"""

import sys
import logging
import subprocess
import time
import os
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
log = logging.getLogger(__name__)


def run_command(cmd, name="Task", timeout=3600):
    """Run a shell command and return success/failure."""
    log.info(f"Starting: {name}")
    log.debug(f"Command: {cmd}")

    start_time = time.time()
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            timeout=timeout,
            capture_output=True,
            text=True,
        )

        elapsed = time.time() - start_time
        if result.returncode == 0:
            log.info(f"✅ {name} completed in {elapsed:.1f}s")
            return True
        else:
            log.error(f"❌ {name} failed (exit code {result.returncode})")
            if result.stderr:
                log.error(f"  stderr: {result.stderr[:500]}")
            return False

    except subprocess.TimeoutExpired:
        log.error(f"❌ {name} timeout after {timeout}s")
        return False
    except Exception as e:
        log.error(f"❌ {name} error: {e}")
        return False


def run_tier_0():
    """Run Tier 0: Stock symbols."""
    log.info("\n" + "=" * 80)
    log.info("TIER 0: Stock Symbols")
    log.info("=" * 80)

    cmd = "python3 loaders/loadstocksymbols.py"
    return run_command(cmd, "Tier 0: Stock symbols", timeout=600)


def run_tier_1():
    """Run Tier 1: Price data."""
    log.info("\n" + "=" * 80)
    log.info("TIER 1: Price Data")
    log.info("=" * 80)

    loaders = [
        ("loaders/loadpricedaily.py", "Daily prices", 1200),
        ("loaders/loadetfpricedaily.py", "ETF daily prices", 300),
        ("loaders/load_price_aggregate.py", "Price aggregates (weekly/monthly)", 300),
        ("loaders/load_etf_price_aggregate.py", "ETF aggregates", 300),
        ("loaders/loadmarketindices.py", "Market indices", 300),
    ]

    results = {}
    for loader_file, name, timeout in loaders:
        if os.path.exists(loader_file):
            results[name] = run_command(f"python3 {loader_file}", name, timeout)
        else:
            log.warning(f"⚠️  {loader_file} not found, skipping")

    passed = sum(1 for v in results.values() if v)
    failed = len(results) - passed
    log.info(f"\nTier 1 Summary: {passed}/{len(results)} loaders passed")
    return failed == 0


def run_tier_2():
    """Run Tier 2: Reference data."""
    log.info("\n" + "=" * 80)
    log.info("TIER 2: Reference Data")
    log.info("=" * 80)

    loaders = [
        # Company data
        ("loaders/loadcompanyprofile.py", "Company profiles", 300),
        # Earnings data
        ("loaders/loadearningshistory.py", "Earnings history", 300),
        ("loaders/loadearningsrevisions.py", "Earnings revisions", 300),
        ("loaders/loadearningsestimates.py", "Earnings estimates", 300),
        ("loaders/load_earnings_calendar.py", "Earnings calendar", 300),
        # Sentiment
        ("loaders/loadanalystsentiment.py", "Analyst sentiment", 300),
        ("loaders/loadanalystupgradedowngrade.py", "Analyst upgrades/downgrades", 300),
        # Financials (annual)
        ("loaders/load_income_statement.py --period annual", "Annual income statement", 600),
        ("loaders/load_balance_sheet.py --period annual", "Annual balance sheet", 600),
        ("loaders/load_cash_flow.py --period annual", "Annual cash flow", 600),
        # Financials (quarterly)
        ("loaders/load_income_statement.py --period quarterly", "Quarterly income statement", 600),
        ("loaders/load_balance_sheet.py --period quarterly", "Quarterly balance sheet", 600),
        ("loaders/load_cash_flow.py --period quarterly", "Quarterly cash flow", 600),
        # Economic data
        ("loaders/loadecondata.py", "Economic data", 300),
        ("loaders/loadaaiidata.py", "AAII data", 300),
        ("loaders/loadfeargreed.py", "Fear & Greed index", 300),
        # Market structure
        ("loaders/loadsectors.py", "Sectors", 300),
        ("loaders/loadindustryranking.py", "Industry rankings", 300),
        ("loaders/loadseasonality.py", "Seasonality", 300),
        ("loaders/loadnaaim.py", "NAAIM data", 300),
    ]

    results = {}
    for loader_cmd, name, timeout in loaders:
        loader_file = loader_cmd.split()[0]
        if os.path.exists(loader_file):
            results[name] = run_command(f"python3 {loader_cmd}", name, timeout)
        else:
            log.warning(f"⚠️  {loader_file} not found, skipping")

    passed = sum(1 for v in results.values() if v)
    failed = len(results) - passed
    log.info(f"\nTier 2 Summary: {passed}/{len(results)} loaders passed")
    return failed == 0


def validate_data():
    """Validate data quality in database."""
    log.info("\n" + "=" * 80)
    log.info("DATA VALIDATION")
    log.info("=" * 80)

    try:
        from utils.db_connection import get_db_connection

        conn = get_db_connection()
        cur = conn.cursor()

        # Check each table
        tables = [
            ("stocks", "Stock symbols"),
            ("price_daily", "Daily prices"),
            ("price_weekly", "Weekly prices"),
            ("price_monthly", "Monthly prices"),
            ("earnings_calendar", "Earnings calendar"),
            ("income_statement_annual", "Annual income statements"),
            ("balance_sheet_annual", "Annual balance sheets"),
            ("cash_flow_annual", "Annual cash flows"),
        ]

        log.info("\nData counts by table:")
        for table, description in tables:
            try:
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                count = cur.fetchone()[0]
                log.info(f"  {description:<35} {count:>10,} rows")
            except Exception as e:
                log.warning(f"  {description:<35} (table missing or error)")

        cur.close()
        return True

    except Exception as e:
        log.warning(f"Database validation failed: {e}")
        return None


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Run full data load pipeline")
    parser.add_argument("--tier", choices=["0", "1", "2", "3", "all"], default="all")
    parser.add_argument("--validate-only", action="store_true", help="Only validate data")
    parser.add_argument("--local", action="store_true", help="Load to local database")
    parser.add_argument("--aws", action="store_true", help="Load to AWS RDS")
    args = parser.parse_args()

    if not args.local and not args.aws:
        args.local = True  # Default to local

    results = {}

    if args.validate_only:
        return 0 if validate_data() else 1

    # Run loaders by tier
    if args.tier in ("0", "all"):
        results["tier_0"] = run_tier_0()
        if not results["tier_0"]:
            log.error("Tier 0 must pass before continuing")
            return 1

    if args.tier in ("1", "all"):
        results["tier_1"] = run_tier_1()

    if args.tier in ("2", "all"):
        results["tier_2"] = run_tier_2()

    # Validate
    if args.tier == "all":
        log.info("\nValidating loaded data...")
        validate_data()

    # Summary
    log.info("\n" + "=" * 80)
    log.info("FINAL SUMMARY")
    log.info("=" * 80)

    for test_name, result in results.items():
        status = "✅ PASSED" if result else "❌ FAILED"
        log.info(f"{test_name}: {status}")

    all_passed = all(results.values()) if results else True
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
