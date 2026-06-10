#!/usr/bin/env python3
"""
Diagnostic script to identify data loading issues blocking step functions.

Checks:
1. Database connectivity and schema
2. Critical table availability and row counts
3. Data freshness (Phase 1 checks)
4. Loader status in data_loader_status table
5. Recent failures in orchestrator_execution_log
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from utils.database_context import DatabaseContext

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

ET = ZoneInfo("America/New_York")
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RESET = "\033[0m"

def check_database_connectivity():
    """Test database connection."""
    logger.info("\n" + "="*60)
    logger.info("STEP 1: DATABASE CONNECTIVITY")
    logger.info("="*60)
    try:
        with DatabaseContext('read') as cur:
            cur.execute("SELECT version()")
            version = cur.fetchone()[0]
            logger.info(f"{GREEN}✓{RESET} Database connected")
            logger.info(f"  PostgreSQL: {version[:50]}...")
        return True
    except Exception as e:
        logger.error(f"{RED}✗{RESET} Database connection failed: {e}")
        return False

def check_schema():
    """Verify critical tables exist."""
    logger.info("\n" + "="*60)
    logger.info("STEP 2: SCHEMA VERIFICATION")
    logger.info("="*60)

    critical_tables = [
        'stock_symbols',
        'price_daily',
        'technical_data_daily',
        'market_health_daily',
        'trend_template_data',
        'buy_sell_daily',
        'signal_quality_scores',
        'algo_metrics_daily',
        'swing_trader_scores',
        'algo_performance_daily',
        'data_loader_status',
        'orchestrator_execution_log',
    ]

    all_exist = True
    try:
        with DatabaseContext('read') as cur:
            for table in critical_tables:
                cur.execute("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.tables
                        WHERE table_name = %s
                    )
                """, (table,))
                exists = cur.fetchone()[0]
                status = f"{GREEN}✓{RESET}" if exists else f"{RED}✗{RESET}"
                logger.info(f"  {status} {table}")
                if not exists:
                    all_exist = False
        return all_exist
    except Exception as e:
        logger.error(f"{RED}✗{RESET} Schema check failed: {e}")
        return False

def check_data_freshness():
    """Check Phase 1 data freshness criteria."""
    logger.info("\n" + "="*60)
    logger.info("STEP 3: DATA FRESHNESS (PHASE 1 CRITERIA)")
    logger.info("="*60)

    try:
        with DatabaseContext('read') as cur:
            # Most recent price date
            cur.execute("SELECT MAX(date) FROM price_daily")
            max_date = cur.fetchone()[0]

            if max_date is None:
                logger.error(f"{RED}✗{RESET} price_daily is empty")
                return False

            logger.info(f"  Most recent price date: {max_date}")

            # Symbol coverage
            cur.execute("""
                SELECT COUNT(DISTINCT symbol)
                FROM price_daily WHERE date = %s
            """, (max_date,))
            symbols_today = cur.fetchone()[0] or 0

            # Prior day coverage
            cur.execute("""
                SELECT COUNT(DISTINCT symbol)
                FROM price_daily WHERE date = (
                    SELECT MAX(date) FROM price_daily WHERE date < %s
                )
            """, (max_date,))
            symbols_prior = cur.fetchone()[0] or symbols_today

            coverage_pct = (symbols_today / max(symbols_prior, 1)) * 100
            logger.info(f"  Symbols on {max_date}: {symbols_today}")
            logger.info(f"  Symbols prior day: {symbols_prior}")
            logger.info(f"  Coverage: {coverage_pct:.1f}%")

            # Check Phase 1 criteria
            today = date.today()
            last_trading_day = today - timedelta(days=1)

            passes_freshness = max_date >= last_trading_day and symbols_today >= 1000 and coverage_pct >= 95
            if passes_freshness:
                logger.info(f"{GREEN}✓{RESET} Phase 1 freshness check PASSES")
            else:
                logger.error(f"{RED}✗{RESET} Phase 1 freshness check FAILS")
                if max_date < last_trading_day:
                    logger.error(f"    - Price data is stale: {max_date} < {last_trading_day}")
                if symbols_today < 1000:
                    logger.error(f"    - Insufficient symbols: {symbols_today} < 1000")
                if coverage_pct < 95:
                    logger.error(f"    - Coverage below 95%: {coverage_pct:.1f}%")

            return passes_freshness
    except Exception as e:
        logger.error(f"{RED}✗{RESET} Data freshness check failed: {e}")
        return False

def check_loader_status():
    """Check status of critical loaders."""
    logger.info("\n" + "="*60)
    logger.info("STEP 4: LOADER STATUS")
    logger.info("="*60)

    critical_loaders = [
        'stock_symbols',
        'stock_prices_daily',
        'technical_data_daily',
        'market_health_daily',
        'trend_template_data',
        'buy_sell_daily',
        'signal_quality_scores',
        'algo_metrics_daily',
        'swing_trader_scores',
    ]

    try:
        with DatabaseContext('read') as cur:
            for loader_name in critical_loaders:
                cur.execute("""
                    SELECT status, last_updated
                    FROM data_loader_status
                    WHERE table_name = %s
                    ORDER BY last_updated DESC LIMIT 1
                """, (loader_name,))
                row = cur.fetchone()

                if row:
                    status, last_updated = row
                    age_min = (datetime.now(ET) - last_updated).total_seconds() / 60
                    color = GREEN if status == 'COMPLETED' else YELLOW if status == 'RUNNING' else RED
                    logger.info(f"  {color}{status:10}{RESET} {loader_name:30} (last {age_min:.0f} min ago)")
                else:
                    logger.info(f"  {RED}NO DATA  {RESET} {loader_name:30}")
        return True
    except Exception as e:
        logger.error(f"{RED}✗{RESET} Loader status check failed: {e}")
        return False

def check_recent_orchestrator_runs():
    """Check recent orchestrator runs for failures."""
    logger.info("\n" + "="*60)
    logger.info("STEP 5: RECENT ORCHESTRATOR RUNS")
    logger.info("="*60)

    try:
        with DatabaseContext('read') as cur:
            cur.execute("""
                SELECT run_id, run_date, overall_status, summary
                FROM orchestrator_execution_log
                WHERE run_date >= CURRENT_DATE - 7
                ORDER BY run_date DESC, run_id DESC
                LIMIT 10
            """)
            runs = cur.fetchall()

            if not runs:
                logger.info(f"  {YELLOW}No recent runs found{RESET}")
                return False

            for run_id, run_date, status, summary in runs:
                color = GREEN if status == 'success' else RED
                logger.info(f"  {color}{status:8}{RESET} {run_date} {run_id}")
                if 'halt' in str(status).lower():
                    logger.info(f"    → {summary}")

            # Check if today has had any runs
            cur.execute("""
                SELECT COUNT(*) FROM orchestrator_execution_log
                WHERE run_date = CURRENT_DATE
            """)
            today_runs = cur.fetchone()[0]

            if today_runs == 0:
                logger.error(f"{RED}✗{RESET} No orchestrator runs TODAY")
                return False
            else:
                logger.info(f"{GREEN}✓{RESET} {today_runs} runs today")
                return True

    except Exception as e:
        logger.error(f"{RED}✗{RESET} Orchestrator run check failed: {e}")
        return False

def check_algo_performance_columns():
    """Verify new algo_performance_daily columns exist."""
    logger.info("\n" + "="*60)
    logger.info("STEP 6: SCHEMA MIGRATION (algo_performance_daily)")
    logger.info("="*60)

    required_columns = [
        'win_rate_all',
        'total_trades',
        'num_wins',
        'num_losses',
        'profit_factor',
        'avg_win',
        'avg_loss',
    ]

    try:
        with DatabaseContext('read') as cur:
            cur.execute("""
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'algo_performance_daily'
            """)
            existing_columns = {row[0] for row in cur.fetchall()}

            all_exist = True
            for col in required_columns:
                exists = col in existing_columns
                status = f"{GREEN}✓{RESET}" if exists else f"{RED}✗{RESET}"
                logger.info(f"  {status} {col}")
                if not exists:
                    all_exist = False

            return all_exist
    except Exception as e:
        logger.error(f"{RED}✗{RESET} Schema migration check failed: {e}")
        return False

def main():
    logger.info("\n" + "█"*60)
    logger.info("DATA LOADING DIAGNOSTIC")
    logger.info("█"*60)

    checks = [
        ("Database Connectivity", check_database_connectivity),
        ("Schema Verification", check_schema),
        ("Data Freshness", check_data_freshness),
        ("Loader Status", check_loader_status),
        ("Recent Orchestrator Runs", check_recent_orchestrator_runs),
        ("Schema Migration", check_algo_performance_columns),
    ]

    results = []
    for name, check_fn in checks:
        try:
            result = check_fn()
            results.append((name, result))
        except Exception as e:
            logger.error(f"{RED}✗{RESET} {name} crashed: {e}")
            results.append((name, False))

    logger.info("\n" + "="*60)
    logger.info("SUMMARY")
    logger.info("="*60)
    for name, passed in results:
        status = f"{GREEN}PASS{RESET}" if passed else f"{RED}FAIL{RESET}"
        logger.info(f"  {status} {name}")

    all_passed = all(passed for _, passed in results)
    if all_passed:
        logger.info(f"\n{GREEN}All checks passed!{RESET}")
        return 0
    else:
        logger.error(f"\n{RED}Some checks failed. See details above.{RESET}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
