#!/usr/bin/env python3
"""System readiness verification - Check all components for orchestrator execution."""

import sys
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import date, timedelta
from utils.db_connection import get_db_connection
from config.credential_helper import get_db_config
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def check_database():
    """Verify database connectivity."""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.close()
        conn.close()
        logger.info("✅ Database: Connected")
        return True
    except Exception as e:
        logger.error(f"❌ Database: {e}")
        return False

def check_tables():
    """Check critical tables have data."""
    conn = get_db_connection()
    cur = conn.cursor()

    tables = {
        'price_daily': 'Latest stock prices',
        'technical_data_daily': 'Technical indicators (RSI, MACD, etc.)',
        'buy_sell_daily': 'Buy/sell signals',
        'signal_quality_scores': 'Signal quality scores (Phase 1 required)',
        'trend_template_data': 'Trend template scores',
        'market_health_daily': 'Market health (SPY, VIX)',
    }

    issues = []
    for table, desc in tables.items():
        try:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            count = cur.fetchone()[0]
            if count > 0:
                logger.info(f"✅ {table:25s}: {count:,} rows ({desc})")
            else:
                logger.warning(f"⚠️  {table:25s}: EMPTY ({desc})")
                issues.append(table)
        except Exception as e:
            logger.error(f"❌ {table:25s}: {str(e)[:50]}")
            issues.append(table)

    cur.close()
    conn.close()
    return len(issues) == 0, issues

def check_phase1_data():
    """Verify Phase 1 data freshness requirements."""
    conn = get_db_connection()
    cur = conn.cursor()

    # Check latest dates for critical tables
    critical_tables = {
        'price_daily': 'date',
        'buy_sell_daily': 'date',
        'technical_data_daily': 'date',
        'signal_quality_scores': 'date',
        'trend_template_data': 'date',
        'market_health_daily': 'date',
    }

    today = date.today()
    max_stale_days = 7  # Lenient for DEV mode

    all_fresh = True
    for table, date_col in critical_tables.items():
        try:
            cur.execute(f"SELECT MAX({date_col}) FROM {table}")
            result = cur.fetchone()
            latest_date = result[0] if result and result[0] else None

            if latest_date is None:
                logger.warning(f"⚠️  {table:25s}: No data (EMPTY)")
                all_fresh = False
            else:
                age = (today - latest_date).days
                if age <= max_stale_days:
                    logger.info(f"✅ {table:25s}: {latest_date} ({age} days old)")
                else:
                    logger.warning(f"⚠️  {table:25s}: {latest_date} ({age} days old - STALE)")
                    all_fresh = False
        except Exception as e:
            logger.error(f"❌ {table:25s}: {str(e)[:50]}")
            all_fresh = False

    cur.close()
    conn.close()
    return all_fresh

def check_positions():
    """Check current open positions."""
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT symbol, quantity, entry_price, current_price,
                   ROUND(((current_price - entry_price) / entry_price * 100)::numeric, 2) as pnl_pct
            FROM algo_positions
            WHERE status = 'open'
            ORDER BY symbol
        """)
        positions = cur.fetchall()

        if positions:
            logger.info(f"\n📊 OPEN POSITIONS ({len(positions)} trades):")
            for row in positions:
                symbol, qty, entry, current, pnl = row
                logger.info(f"   {symbol}: {qty} @ ${entry} → ${current} ({pnl:+.1f}%)")
        else:
            logger.info("📊 OPEN POSITIONS: None")

    except Exception as e:
        logger.warning(f"Could not retrieve positions: {e}")

    cur.close()
    conn.close()

def main():
    """Run all checks."""
    logger.info("=" * 60)
    logger.info("SYSTEM READINESS CHECK")
    logger.info("=" * 60)

    print()
    db_ok = check_database()
    print()

    if not db_ok:
        logger.error("Cannot proceed - database not connected")
        return False

    tables_ok, missing = check_tables()
    print()

    freshness_ok = check_phase1_data()
    print()

    check_positions()
    print()

    logger.info("=" * 60)
    if freshness_ok:
        logger.info("✅ SYSTEM READY FOR ORCHESTRATOR")
        logger.info("   - All critical tables have fresh data")
        logger.info("   - Phase 1 data freshness checks will pass")
        logger.info("   - Orchestrator can execute")
    else:
        logger.warning("⚠️  SYSTEM HAS DATA QUALITY ISSUES")
        if missing:
            logger.warning(f"   - Empty tables: {', '.join(missing)}")
        logger.warning("   - Orchestrator may halt on Phase 1")
        logger.warning("   - Consider running loaders or seeding test data")
    logger.info("=" * 60)

    return freshness_ok

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
