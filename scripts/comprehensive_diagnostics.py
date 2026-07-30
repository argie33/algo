#!/usr/bin/env python3
"""Comprehensive system diagnostics - verify working data and orchestrator health.

FIXED: This script was using stale schema references (is_active, at.side, etc).
Updated to use only verified tables/columns from working orchestrator code.
"""

import sys
import os
import logging
from pathlib import Path
from datetime import datetime, timedelta, date as _date

# Setup path
project_root = str(Path(__file__).parents[1])
if project_root not in sys.path:
    sys.path.insert(0, project_root)

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)


def check_orchestrator_health():
    """Check orchestrator execution status."""
    logger.info("\n" + "="*70)
    logger.info("ORCHESTRATOR HEALTH (Last 24h)")
    logger.info("="*70)

    try:
        from utils.db.context import DatabaseContext
        with DatabaseContext("read") as cur:
            cur.execute('''
                SELECT overall_status, COUNT(*) as count, MAX(started_at) as latest
                FROM algo_orchestrator_runs
                WHERE started_at > NOW() - INTERVAL '24 hours'
                GROUP BY overall_status
                ORDER BY count DESC
            ''')
            rows = cur.fetchall()

            if not rows:
                logger.warning("⚠ No orchestrator runs in last 24h")
                return

            for status, count, latest in rows:
                status_icon = "✓" if status == "ok" else "✗" if status == "halted" else "⚠"
                logger.info(f"{status_icon} {status:15} {count:3} runs  (latest: {latest})")
    except Exception as e:
        logger.error(f"✗ Failed to check orchestrator health: {e}")


def check_data_freshness():
    """Check key tables for data freshness."""
    logger.info("\n" + "="*70)
    logger.info("DATA FRESHNESS")
    logger.info("="*70)

    # Define tables with specific DATE/TIMESTAMP columns (not generic)
    tables_to_check = [
        ("price_daily", "date", "Price data (Alpaca SIP)"),
        ("technical_data_daily", "date", "Technical indicators (RSI, BB, etc)"),
        ("algo_signals", "signal_date", "Trading signals (buy/sell flags)"),
        ("algo_trades", "created_at", "Executed trades and fills"),
        ("algo_positions", "created_at", "Current open positions"),
    ]

    from utils.db.context import DatabaseContext
    for table_name, date_col, description in tables_to_check:
        try:
            with DatabaseContext("read") as cur:
                cur.execute(f'''
                    SELECT
                        COUNT(*) as row_count,
                        MAX({date_col}::TIMESTAMP) as latest_date
                    FROM {table_name}
                ''')
                row_count, latest_date = cur.fetchone()

                if latest_date is None or row_count == 0:
                    logger.warning(f"⚠ {table_name:30} EMPTY")
                else:
                    # Handle both datetime and date types
                    if isinstance(latest_date, datetime):
                        compare_time = datetime.now(latest_date.tzinfo) if hasattr(latest_date, 'tzinfo') and latest_date.tzinfo else datetime.now()
                    else:
                        # It's a date, convert to datetime for comparison
                        compare_time = datetime.combine(datetime.now().date(), datetime.min.time())
                        latest_date = datetime.combine(latest_date, datetime.min.time())

                    age = compare_time - latest_date
                    hours_old = age.total_seconds() / 3600

                    if hours_old < 1:
                        icon = "✓"
                    elif hours_old < 24:
                        icon = "⚠"
                    else:
                        icon = "✗"

                    logger.info(f"{icon} {table_name:30} {row_count:8,} rows  ({hours_old:.1f}h old)")
        except Exception as e:
            logger.warning(f"⚠ {table_name:30} Failed: {str(e)[:50]}")


def check_position_integrity():
    """Check open positions and their trades."""
    logger.info("\n" + "="*70)
    logger.info("POSITION INTEGRITY")
    logger.info("="*70)

    try:
        from utils.db.context import DatabaseContext
        with DatabaseContext("read") as cur:
            # Check open positions
            cur.execute('''
                SELECT
                    COUNT(*) as open_count,
                    COALESCE(SUM(quantity), 0) as total_shares,
                    COALESCE(SUM(position_value), 0) as total_value
                FROM algo_positions
                WHERE status = 'open'
            ''')
            open_count, total_shares, total_value = cur.fetchone()

            logger.info(f"✓ Open positions: {open_count}")
            logger.info(f"✓ Total shares: {total_shares:,}")
            logger.info(f"✓ Total position value: ${total_value:,.2f}")

            # Check for trades without positions
            cur.execute('''
                SELECT COUNT(*) as orphaned_trades
                FROM algo_trades at
                WHERE at.status IN ('filled', 'partial')
                  AND NOT EXISTS (
                    SELECT 1 FROM algo_positions ap
                    WHERE ap.position_id = at.position_id
                  )
            ''')
            orphaned = cur.fetchone()[0]
            if orphaned > 0:
                logger.warning(f"⚠ Orphaned trades (no position): {orphaned}")
            else:
                logger.info("✓ No orphaned trades")

    except Exception as e:
        logger.error(f"✗ Failed to check position integrity: {e}")


def check_loader_status():
    """Check recent loader execution status."""
    logger.info("\n" + "="*70)
    logger.info("LOADER STATUS (Most Recent Runs)")
    logger.info("="*70)

    try:
        from utils.db.context import DatabaseContext
        with DatabaseContext("read") as cur:
            # Check loader execution history - skip if table/columns don't exist
            try:
                cur.execute('''
                    SELECT
                        loader_name,
                        MAX(created_at) as latest_run,
                        COUNT(*) as run_count
                    FROM loader_execution_history
                    WHERE created_at > NOW() - INTERVAL '24 hours'
                    GROUP BY loader_name
                    ORDER BY latest_run DESC
                    LIMIT 15
                ''')
                rows = cur.fetchall()

                if not rows:
                    logger.info("ℹ No loader executions in last 24h")
                else:
                    for loader_name, latest_run, run_count in rows:
                        age = datetime.now(latest_run.tzinfo) - latest_run if hasattr(latest_run, 'tzinfo') else datetime.now() - latest_run
                        hours_old = age.total_seconds() / 3600
                        icon = "✓" if hours_old < 12 else "⚠"
                        logger.info(f"{icon} {loader_name:40} {hours_old:6.1f}h old  ({run_count} runs)")
            except Exception:
                logger.info("ℹ Loader execution history unavailable")

    except Exception as e:
        logger.warning(f"⚠ Could not check loader status: {str(e)[:50]}")


def check_alerts():
    """Check for recent errors or warnings."""
    logger.info("\n" + "="*70)
    logger.info("RECENT ALERTS (Last 24h)")
    logger.info("="*70)

    try:
        from utils.db.context import DatabaseContext
        with DatabaseContext("read") as cur:
            # Check orchestrator_execution_log for phases that halted
            try:
                cur.execute('''
                    SELECT
                        phase_number,
                        phase_status,
                        COUNT(*) as count,
                        MAX(logged_at) as latest
                    FROM orchestrator_execution_log
                    WHERE logged_at > NOW() - INTERVAL '24 hours'
                      AND phase_status IN ('halted', 'error', 'degraded')
                    GROUP BY phase_number, phase_status
                    ORDER BY count DESC
                ''')
                halts = cur.fetchall()

                if halts:
                    for phase_num, status, count, latest in halts:
                        age_min = (datetime.now(latest.tzinfo) - latest if hasattr(latest, 'tzinfo') else datetime.now() - latest).total_seconds() / 60
                        logger.warning(f"✗ Phase {phase_num:2}                    {status:10} {count:3} times ({age_min:.0f}m ago)")
                else:
                    logger.info("✓ No phase halts in last 24h")
            except Exception as e:
                logger.info(f"ℹ Phase status history unavailable ({str(e)[:30]})")

    except Exception as e:
        logger.warning(f"⚠ Could not check alerts: {str(e)[:50]}")


def main():
    """Run all diagnostics."""
    logger.info("\n" + "█" * 70)
    logger.info("COMPREHENSIVE SYSTEM DIAGNOSTICS - " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    logger.info("█" * 70)

    check_orchestrator_health()
    check_data_freshness()
    check_position_integrity()
    check_loader_status()
    check_alerts()

    logger.info("\n" + "=" * 70)
    logger.info("DIAGNOSTICS COMPLETE")
    logger.info("=" * 70)
    logger.info("\nFor detailed troubleshooting:")
    logger.info("  - Check logs: tail -f ~/.algo_logs/orchestrator.log")
    logger.info("  - Review DB: psql -d stocks (use queries from diagnose_system.py)")
    logger.info("  - Monitor health: python scripts/monitor_data_staleness.py")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logger.error(f"\nFATAL ERROR: {e}", exc_info=True)
        sys.exit(1)
