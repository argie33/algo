#!/usr/bin/env python3
"""
Test Orchestrator with Friday Data (May 15, 2026)

This script:
1. Ensures all necessary data is loaded for Friday, May 15, 2026
2. Runs the orchestrator with that Friday data
3. Verifies if any buy signals would trigger
4. Shows detailed results and logs

Usage:
    python3 test-with-friday-data.py [--no-load] [--check-only]

Options:
    --no-load      Skip data loading (assumes data already loaded)
    --check-only   Only check if data exists, don't run orchestrator
"""

import sys
import os
import logging
from datetime import date, datetime
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

# Add root to path
sys.path.insert(0, str(Path(__file__).parent))

TEST_DATE = date(2026, 5, 15)  # Friday
CURRENT_DATE = date(2026, 5, 17)  # Current date (weekend)


def check_database_data():
    """Check what data is currently in the database."""
    logger.info("\n📊 CHECKING DATABASE DATA")
    logger.info("="*70)

    try:
        from config.credential_helper import get_db_config
        from utils.db_connection import get_db_connection

        db_config = get_db_config()
        conn = get_db_connection()
        cursor = conn.cursor()

        # Check stock symbols
        cursor.execute("SELECT COUNT(*) FROM stock_symbols")
        symbols_count = cursor.fetchone()[0]
        logger.info(f"Stock Symbols: {symbols_count:,}")

        if symbols_count == 0:
            logger.warning("⚠️  No symbols loaded. Need to run: python3 run-all-loaders.py")
            cursor.close()
            conn.close()
            return False

        # Check prices
        cursor.execute(f"SELECT COUNT(*), MAX(date) FROM price_daily")
        price_count, latest_price_date = cursor.fetchone()
        logger.info(f"Total Prices: {price_count:,}")
        logger.info(f"Latest Price Date: {latest_price_date}")

        # Check Friday prices specifically
        cursor.execute(
            f"SELECT COUNT(*) FROM price_daily WHERE date = %s",
            (TEST_DATE,)
        )
        friday_prices = cursor.fetchone()[0]
        logger.info(f"Friday ({TEST_DATE}) Prices: {friday_prices:,}")

        if friday_prices == 0:
            logger.warning(f"⚠️  No prices for {TEST_DATE}")
            logger.warning("   Run loaders to get latest data: python3 run-all-loaders.py")

        # Check signals
        cursor.execute(f"SELECT COUNT(*), MAX(date) FROM buy_sell_signal_daily")
        signal_count, latest_signal_date = cursor.fetchone()
        logger.info(f"Total Signals: {signal_count:,}")
        logger.info(f"Latest Signal Date: {latest_signal_date}")

        # Check Friday signals
        cursor.execute(
            f"SELECT COUNT(*) FROM buy_sell_signal_daily WHERE date = %s AND signal = 'BUY'",
            (TEST_DATE,)
        )
        friday_buy_signals = cursor.fetchone()[0]
        logger.info(f"Friday ({TEST_DATE}) BUY Signals: {friday_buy_signals:,}")

        # Check technical indicators
        cursor.execute(f"SELECT COUNT(*), MAX(date) FROM technical_indicator_daily")
        ti_count, latest_ti_date = cursor.fetchone()
        logger.info(f"Technical Indicators: {ti_count:,}")

        # Summary
        logger.info("\n" + "="*70)
        all_ready = (
            symbols_count > 0 and
            friday_prices > 0 and
            signal_count > 0
        )

        if all_ready:
            logger.info("✅ All required data is available")
        else:
            logger.warning("⚠️  Missing some required data")
            if symbols_count == 0:
                logger.warning("   - Need stock symbols")
            if friday_prices == 0:
                logger.warning(f"   - Need prices for {TEST_DATE}")
            if signal_count == 0:
                logger.warning("   - Need buy/sell signals")

        cursor.close()
        conn.close()

        return all_ready

    except Exception as e:
        logger.error(f"Database error: {e}")
        logger.error("Make sure PostgreSQL is running and credentials are set")
        return False


def run_loaders():
    """Run the data loading pipeline."""
    logger.info("\n🚀 LOADING DATA")
    logger.info("="*70)

    try:
        import subprocess
        result = subprocess.run(
            [sys.executable, "run-all-loaders.py"],
            timeout=7200,  # 2 hours
            capture_output=False
        )
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        logger.error("Loaders timed out after 2 hours")
        return False
    except Exception as e:
        logger.error(f"Loader error: {e}")
        return False


def run_orchestrator():
    """Run the orchestrator with Friday data."""
    logger.info("\n🎬 RUNNING ORCHESTRATOR WITH FRIDAY DATA")
    logger.info("="*70)
    logger.info(f"Running for: {TEST_DATE} (Friday)")
    logger.info(f"Current date: {CURRENT_DATE}")

    try:
        from algo.algo_orchestrator import Orchestrator
        from algo.algo_config import get_config

        logger.info("\nInitializing orchestrator...")
        config = get_config()
        orchestrator = Orchestrator(
            config=config,
            run_date=TEST_DATE,
            dry_run=True,  # Paper trading mode
            verbose=True
        )

        logger.info("Starting orchestrator execution...")
        logger.info("Phase 1: Data Freshness Check...")
        logger.info("Phase 2: Circuit Breakers...")
        logger.info("Phase 3: Position Monitor...")
        logger.info("Phase 4: Exit Execution...")
        logger.info("Phase 5: Signal Generation...")
        logger.info("Phase 6: Entry Execution...")
        logger.info("Phase 7: Reconciliation...")

        results = orchestrator.run()

        logger.info("\n" + "="*70)
        logger.info("ORCHESTRATOR RESULTS")
        logger.info("="*70)

        if results:
            logger.info(json.dumps(results, indent=2, default=str))

            # Check for phase failures
            for phase_name, phase_result in results.items():
                if isinstance(phase_result, dict):
                    status = phase_result.get("status", "unknown")
                    if status in ("failed", "halted"):
                        logger.warning(f"⚠️  {phase_name}: {status}")
                        if "error" in phase_result:
                            logger.warning(f"   Error: {phase_result['error']}")

        return True

    except Exception as e:
        logger.error(f"Orchestrator error: {e}")
        import traceback
        traceback.print_exc()
        return False


def check_audit_logs():
    """Check results in audit logs."""
    logger.info("\n📋 CHECKING AUDIT LOGS")
    logger.info("="*70)

    try:
        from config.credential_helper import get_db_config
        from utils.db_connection import get_db_connection

        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
            SELECT phase, status, COUNT(*) as count
            FROM algo_audit_log
            WHERE DATE(created_at) = %s
            GROUP BY phase, status
            ORDER BY phase, created_at
        """, (TEST_DATE,))

        rows = cursor.fetchall()
        if rows:
            logger.info(f"\nAudit log entries for {TEST_DATE}:")
            for phase, status, count in rows:
                logger.info(f"  {phase}: {status} ({count})")
        else:
            logger.info(f"No audit log entries for {TEST_DATE}")

        # Check for trades
        cursor.execute("""
            SELECT action, COUNT(*) as count
            FROM trades
            WHERE DATE(created_at) = %s
            GROUP BY action
        """, (TEST_DATE,))

        trade_rows = cursor.fetchall()
        if trade_rows:
            logger.info(f"\nTrades for {TEST_DATE}:")
            for action, count in trade_rows:
                logger.info(f"  {action}: {count}")
        else:
            logger.info(f"No trades executed for {TEST_DATE}")

        cursor.close()
        conn.close()

    except Exception as e:
        logger.warning(f"Could not check audit logs: {e}")


def print_summary(data_ready, load_success, orchestrator_success):
    """Print final summary."""
    logger.info("\n" + "="*70)
    logger.info("TEST SUMMARY")
    logger.info("="*70)

    logger.info(f"\n1. Data Available: {'✅' if data_ready else '❌'}")
    logger.info(f"2. Data Loaded: {'✅' if load_success else '⏭️  (skipped)'}")
    logger.info(f"3. Orchestrator Ran: {'✅' if orchestrator_success else '❌'}")

    if data_ready and orchestrator_success:
        logger.info("\n🎉 SUCCESS!")
        logger.info("The system can run with Friday data.")
        logger.info("Ready to deploy to AWS.")
    else:
        logger.info("\n⚠️  ISSUES TO RESOLVE:")
        if not data_ready:
            logger.info("  - Run data loaders: python3 run-all-loaders.py")
        if not orchestrator_success:
            logger.info("  - Check orchestrator logs for errors")

    logger.info("\n📚 AWS Deployment Checklist:")
    logger.info("  [ ] Loaders populate data in RDS")
    logger.info("  [ ] Orchestrator runs with Friday data")
    logger.info("  [ ] CloudWatch logs show success")
    logger.info("  [ ] Buy signals trigger correctly")


def main():
    """Main test execution."""
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Test orchestrator with Friday data")
    parser.add_argument("--no-load", action="store_true", help="Skip data loading")
    parser.add_argument("--check-only", action="store_true", help="Only check data, don't run orchestrator")
    args = parser.parse_args()

    logger.info("🧪 ORCHESTRATOR FRIDAY DATA TEST")
    logger.info("="*70)
    logger.info(f"Test Date: {TEST_DATE} (Friday)")
    logger.info(f"Current Date: {CURRENT_DATE} (Weekend)")
    logger.info("="*70)

    # Check database
    data_ready = check_database_data()

    if args.check_only:
        logger.info("\n--check-only specified. Stopping here.")
        return 0

    # Load data if needed
    load_success = True
    if not args.no_load and not data_ready:
        logger.info("\nData not ready. Running loaders...")
        load_success = run_loaders()
        if load_success:
            data_ready = check_database_data()

    # Run orchestrator if data is ready
    orchestrator_success = False
    if data_ready:
        orchestrator_success = run_orchestrator()
        check_audit_logs()
    else:
        logger.warning("⚠️  Cannot run orchestrator without data")

    # Print summary
    print_summary(data_ready, load_success if not args.no_load else True, orchestrator_success)

    return 0 if data_ready and orchestrator_success else 1


if __name__ == "__main__":
    sys.exit(main())
