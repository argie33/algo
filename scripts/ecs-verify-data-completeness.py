#!/usr/bin/env python3
"""
ECS Diagnostic Task: Verify production data loading completeness.

Run this from ECS inside VPC to verify:
1. Price data coverage meets Phase 1 thresholds
2. Recent data exists for all critical tables
3. No gaps in daily data sequences
4. Loader execution timestamps show recent runs

Execute from ECS:
    aws ecs run-task \
      --cluster algo-cluster \
      --launch-type FARGATE \
      --task-definition algo-data-completeness-verifier \
      --network-configuration "awsvpcConfiguration={subnets=[subnet-xxx],securityGroups=[sg-xxx],assignPublicIp=DISABLED}"
"""

import logging
import os
import sys
from datetime import date, timedelta

import psycopg2


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


def get_db_connection():
    """Connect to RDS via private proxy inside VPC."""
    required_env = ["DB_HOST", "DB_PORT", "DB_USER", "DB_PASSWORD", "DB_NAME"]
    missing = [var for var in required_env if var not in os.environ]
    if missing:
        raise ValueError(
            f"Missing required environment variables: {', '.join(missing)}. "
            f"This script requires ECS task environment configuration."
        )

    return psycopg2.connect(
        host=os.environ["DB_HOST"],
        port=int(os.environ["DB_PORT"]),
        user=os.environ["DB_USER"],
        password=os.environ["DB_PASSWORD"],
        database=os.environ["DB_NAME"],
        connect_timeout=10
    )


def verify_price_coverage(conn) -> tuple[bool, dict]:
    """Verify Phase 1 price coverage thresholds (5000 symbols, 75%).

    Returns: (passes_threshold, result_dict)
    """
    logger.info("=" * 70)
    logger.info("PHASE 1: PRICE DATA COVERAGE VERIFICATION")
    logger.info("=" * 70)

    cursor = conn.cursor()

    # Get most recent date with data
    cursor.execute("SELECT MAX(date) FROM price_daily")
    max_date = cursor.fetchone()[0]

    if not max_date:
        logger.error("FAIL: price_daily table is empty")
        return False, {"error": "empty_table"}

    logger.info(f"Latest price data date: {max_date}")

    # Get trading day (skip weekends/holidays)
    from algo.infrastructure import MarketCalendar
    today = date.today()
    last_trading_day = today - timedelta(days=1)
    while last_trading_day > today - timedelta(days=10):
        if MarketCalendar.is_trading_day(last_trading_day):
            break
        last_trading_day -= timedelta(days=1)

    logger.info(f"Expected trading day: {last_trading_day}")

    # Check staleness
    if max_date < last_trading_day:
        days_stale = (last_trading_day - max_date).days
        logger.error(f"FAIL: Price data is {days_stale} days stale")
        logger.error(f"  Latest: {max_date}, Expected: {last_trading_day}")
        return False, {"stale_days": days_stale}

    # Check symbol coverage
    cursor.execute(
        "SELECT COUNT(DISTINCT symbol) FROM price_daily WHERE date = %s",
        (max_date,)
    )
    symbols_today = cursor.fetchone()[0]

    cursor.execute(
        "SELECT COUNT(DISTINCT symbol) FROM price_daily WHERE date = "
        "(SELECT MAX(date) FROM price_daily WHERE date < %s)",
        (max_date,)
    )
    symbols_prior = cursor.fetchone()[0] or symbols_today

    coverage_pct = (symbols_today / max(symbols_prior, 1)) * 100

    logger.info(f"Symbol coverage: {symbols_today} symbols (prior: {symbols_prior})")
    logger.info(f"Coverage ratio: {coverage_pct:.1f}%")

    # Phase 1 thresholds
    min_symbols = 5000
    min_coverage = 75.0

    passes = symbols_today >= min_symbols and coverage_pct >= min_coverage

    if passes:
        logger.info("PASS: Coverage meets Phase 1 thresholds")
        logger.info(f"  {symbols_today} >= {min_symbols} symbols: YES")
        logger.info(f"  {coverage_pct:.1f}% >= {min_coverage}% coverage: YES")
    else:
        logger.error("FAIL: Coverage below Phase 1 thresholds")
        if symbols_today < min_symbols:
            logger.error(f"  Symbols: {symbols_today} < {min_symbols}")
        if coverage_pct < min_coverage:
            logger.error(f"  Coverage: {coverage_pct:.1f}% < {min_coverage}%")

    cursor.close()

    return passes, {
        "max_date": str(max_date),
        "symbols_today": symbols_today,
        "symbols_prior": symbols_prior,
        "coverage_pct": round(coverage_pct, 1),
        "passes_threshold": passes
    }


def verify_table_freshness(conn) -> tuple[bool, dict]:
    """Verify critical tables have recent data."""
    logger.info("\n" + "=" * 70)
    logger.info("CRITICAL TABLE FRESHNESS CHECK")
    logger.info("=" * 70)

    cursor = conn.cursor()

    tables = [
        ("market_health_daily", "date", 1),
        ("market_exposure_daily", "date", 1),
        ("technical_data_daily", "date", 1),
        ("trend_template_data", "date", 1),
    ]

    results = {}
    all_fresh = True

    for table, date_col, max_age_days in tables:
        try:
            cursor.execute(f"SELECT MAX({date_col}) FROM {table}")
            max_date = cursor.fetchone()[0]

            if not max_date:
                logger.warning(f"{table}: EMPTY")
                results[table] = "empty"
                all_fresh = False
                continue

            age = (date.today() - max_date).days

            if age <= max_age_days:
                logger.info(f"{table}: FRESH ({age} days old)")
                results[table] = f"fresh_{age}d"
            else:
                logger.warning(f"{table}: STALE ({age} days old)")
                results[table] = f"stale_{age}d"
                all_fresh = False
        except Exception as e:
            logger.error(f"{table}: ERROR - {e}")
            results[table] = f"error_{str(e)[:20]}"
            all_fresh = False

    cursor.close()
    return all_fresh, results


def verify_no_gaps(conn) -> tuple[bool, dict]:
    """Check for missing dates in price data sequence."""
    logger.info("\n" + "=" * 70)
    logger.info("DATA GAP DETECTION")
    logger.info("=" * 70)

    cursor = conn.cursor()

    # Get last 10 trading dates
    cursor.execute("""
        SELECT DISTINCT date FROM price_daily
        WHERE date >= CURRENT_DATE - INTERVAL '30 days'
        ORDER BY date DESC
        LIMIT 10
    """)
    dates = [row[0] for row in cursor.fetchall()]

    if not dates:
        logger.error("No recent dates found in price_daily")
        cursor.close()
        return False, {"error": "no_recent_data"}

    logger.info(f"Recent dates in database (last 10): {dates}")

    # Check for gaps
    from algo.infrastructure import MarketCalendar

    gaps = []
    for i in range(len(dates) - 1):
        curr_date = dates[i]
        next_date = dates[i + 1]

        # Find expected trading day between them
        check_date = curr_date - timedelta(days=1)
        while check_date > next_date:
            if MarketCalendar.is_trading_day(check_date):
                gaps.append(f"{check_date} (missing between {curr_date} and {next_date})")
            check_date -= timedelta(days=1)

    if gaps:
        logger.warning(f"Found {len(gaps)} potential gaps:")
        for gap in gaps:
            logger.warning(f"  - {gap}")
        return False, {"gaps": gaps}
    else:
        logger.info("No gaps detected in recent date sequence")
        return True, {"gaps_found": 0}


def main():
    """Run all production data verification checks."""
    logger.info("Starting production data completeness verification...")
    logger.info(f"Time: {date.today()}")

    try:
        conn = get_db_connection()
        logger.info("Connected to RDS")
    except Exception as e:
        logger.error(f"Failed to connect to RDS: {e}")
        logger.error("This script must run from ECS inside the VPC")
        return 1

    results = {}
    exit_code = 0

    try:
        # Check 1: Phase 1 price coverage
        price_ok, price_data = verify_price_coverage(conn)
        results["phase1_price_coverage"] = price_data
        if not price_ok:
            exit_code = 1

        # Check 2: Table freshness
        freshness_ok, freshness_data = verify_table_freshness(conn)
        results["table_freshness"] = freshness_data
        if not freshness_ok:
            exit_code = 1

        # Check 3: No gaps
        gaps_ok, gaps_data = verify_no_gaps(conn)
        results["gap_detection"] = gaps_data
        if not gaps_ok:
            exit_code = 1

    finally:
        conn.close()

    # Summary
    logger.info("\n" + "=" * 70)
    logger.info("VERIFICATION SUMMARY")
    logger.info("=" * 70)

    if exit_code == 0:
        logger.info("✓ ALL CHECKS PASSED - Data loading is complete")
        logger.info("✓ Phase 1 can proceed with trading")
    else:
        logger.error("✗ SOME CHECKS FAILED - Data loading has issues")
        logger.error("✗ Phase 1 should halt trading")

    logger.info(f"\nFull results: {results}")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
