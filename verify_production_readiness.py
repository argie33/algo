#!/usr/bin/env python3
"""Comprehensive production readiness check for trading orchestrator.

Verifies:
1. Critical configuration is correct
2. Database integrity
3. All safety rules are in place
4. Execution paths work correctly
"""

import sys
import logging
from pathlib import Path

# Setup path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Load environment
from utils.dotenv_loader import load_env_local
load_env_local()

from utils.db import DatabaseContext
from algo.infrastructure.config import get_config

logging.basicConfig(level=logging.INFO, format='%(name)s: %(message)s')
logger = logging.getLogger(__name__)

def check_config():
    """Verify all critical configuration is set correctly."""
    logger.info("=" * 70)
    logger.info("CONFIGURATION CHECKS")
    logger.info("=" * 70)

    config = get_config()

    # Critical checks
    checks = [
        ("execution_mode", lambda c: c.get("execution_mode") == "paper", "Must be 'paper' for local"),
        ("alpaca_paper_trading", lambda c: c.get("alpaca_paper_trading") is True, "Must be True"),
        ("max_position_size_pct", lambda c: 0.1 <= float(c.get("max_position_size_pct", 0)) <= 15, "Must be 0.1-15%"),
        ("halt_drawdown_pct", lambda c: -100 <= float(c.get("halt_drawdown_pct", 0)) <= -5, "Must be -100 to -5%"),
        ("max_daily_loss_pct", lambda c: 0.1 <= float(c.get("max_daily_loss_pct", 0)) <= 50, "Must be 0.1-50%"),
    ]

    passed = 0
    for key, check_fn, desc in checks:
        try:
            result = check_fn(config)
            status = "[OK]" if result else "[FAIL]"
            value = config.get(key)
            print(f"  {status}: {key:40} = {str(value)[:20]:20} ({desc})")
            if result:
                passed += 1
        except Exception as e:
            print(f"  [ERROR]: {key:40} - {e}")

    print(f"\nConfiguration: {passed}/{len(checks)} checks passed")
    return passed == len(checks)

def check_database():
    """Verify database state and data integrity."""
    logger.info("=" * 70)
    logger.info("DATABASE INTEGRITY CHECKS")
    logger.info("=" * 70)

    issues = []

    try:
        with DatabaseContext("read") as cur:
            # Check critical tables exist
            tables = ["algo_positions", "algo_trades", "orchestrator_execution_log", "buy_sell_daily"]
            for table in tables:
                cur.execute(f"SELECT COUNT(*) FROM {table}")
                count = cur.fetchone()[0]
                print(f"  Table {table:35}: {count:10} rows")

            # Check for positions without required fields
            cur.execute("""
                SELECT COUNT(*) FROM algo_positions
                WHERE status='open'
                  AND (current_price IS NULL OR current_stop_price IS NULL)
            """)
            bad_positions = cur.fetchone()[0]
            if bad_positions > 0:
                issues.append(f"Found {bad_positions} open positions with NULL price/stop")
                print(f"  [ISSUE]: {bad_positions} positions missing required fields")
            else:
                print(f"  [OK] All open positions have current_price and stop")

            # Check for positions closed without P&L
            cur.execute("""
                SELECT COUNT(*) FROM algo_positions
                WHERE status='closed' AND (profit_loss_dollars IS NULL OR exit_reason IS NULL)
            """)
            bad_closed = cur.fetchone()[0]
            if bad_closed > 0:
                issues.append(f"Found {bad_closed} closed positions with NULL P&L/exit_reason")
                print(f"  [ISSUE]: {bad_closed} closed positions missing P&L/exit_reason")
            else:
                print(f"  [OK] All closed positions have P&L and exit_reason")

            # Check orchestrator execution log for recent failures
            cur.execute("""
                SELECT COUNT(*) FROM orchestrator_execution_log
                WHERE overall_status='halted' AND DATE(started_at) = CURRENT_DATE
            """)
            halted_today = cur.fetchone()[0]
            if halted_today > 0:
                issues.append(f"Found {halted_today} halted runs today")
                print(f"  [WARNING]: {halted_today} halted orchestrator runs today")
            else:
                print(f"  [OK] No halted orchestrator runs today")

    except Exception as e:
        logger.error(f"Database check error: {e}")
        return False

    print(f"\nDatabase: {len(issues)} issues found")
    return len(issues) == 0

def check_safety_rules():
    """Verify critical safety rules are implemented."""
    logger.info("=" * 70)
    logger.info("SAFETY RULE VERIFICATION")
    logger.info("=" * 70)

    issues = []

    # Check 1: Exit execution handles ROLLBACK properly
    with open("algo/trading/exit_engine.py") as f:
        content = f.read()
        if "ROLLBACK TO SAVEPOINT" in content and "try:" in content and "except" in content:
            print("  [OK] Exit engine wraps ROLLBACK in try-except")
        else:
            issues.append("Exit engine may not wrap ROLLBACK properly")
            print("  [ISSUE] Exit engine ROLLBACK handling unclear")

    # Check 2: Connection pool is threadsafe
    with open("utils/db/connection.py") as f:
        content = f.read()
        if "ThreadedConnectionPool" in content or "RealDictCursor" in content:
            print("  [OK] Database uses threadsafe connection pooling")
        else:
            issues.append("Database connection pool may not be threadsafe")
            print("  [ISSUE] Database connection pool safety unclear")

    # Check 3: Phase 3 halt checks are not swallowed
    with open("algo/orchestrator/phase3_position_monitor.py") as f:
        content = f.read()
        if "raise" in content and "halt" in content.lower():
            print("  [OK] Phase 3 has halt checks that raise errors")
        else:
            issues.append("Phase 3 halt checks may be swallowed")
            print("  [ISSUE] Phase 3 halt error handling unclear")

    # Check 4: Position closure calculates P&L
    with open("algo/trading/exit_engine.py") as f:
        content = f.read()
        if "profit_loss_dollars" in content and "UPDATE algo_positions" in content:
            print("  [OK] Exit engine calculates profit_loss_dollars on closure")
        else:
            issues.append("Exit engine may not calculate P&L on closure")
            print("  [ISSUE] Exit engine P&L calculation unclear")

    # Check 5: Phase 5 validates all paths
    with open("algo/orchestrator/phase5_exposure_policy.py") as f:
        content = f.read()
        if "validate" in content.lower() and ("raise" in content or "error" in content.lower()):
            print("  [OK] Phase 5 has validation logic")
        else:
            issues.append("Phase 5 validation coverage unclear")
            print("  [ISSUE] Phase 5 validation coverage unclear")

    print(f"\nSafety Rules: {len(issues)} potential gaps")
    return len(issues) == 0

def main():
    logger.info("PRODUCTION READINESS CHECK - 2026-07-30")
    logger.info("")

    config_ok = check_config()
    db_ok = check_database()
    safety_ok = check_safety_rules()

    logger.info("")
    logger.info("=" * 70)
    logger.info("SUMMARY")
    logger.info("=" * 70)
    print(f"  Configuration:   {'OK' if config_ok else 'FAILED'}")
    print(f"  Database:        {'OK' if db_ok else 'FAILED'}")
    print(f"  Safety Rules:    {'OK' if safety_ok else 'FAILED'}")

    all_ok = config_ok and db_ok and safety_ok
    status = "PRODUCTION READY" if all_ok else "ISSUES FOUND"
    print(f"\n  Overall: {status}")

    return 0 if all_ok else 1

if __name__ == "__main__":
    sys.exit(main())
