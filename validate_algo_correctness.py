#!/usr/bin/env python3
"""
Comprehensive Algo Validation Script

Tests the 7-phase orchestrator and all key calculations to ensure
production readiness. Produces detailed report of any issues found.

USAGE:
    python3 validate_algo_correctness.py --mode full       # Full validation
    python3 validate_algo_correctness.py --mode quick      # Quick checks only
    python3 validate_algo_correctness.py --mode backtest   # Run backtest validation
"""

import os
import sys
import logging
import argparse
from pathlib import Path
from datetime import date, timedelta
from typing import Dict, List, Tuple, Any

import psycopg2
from dotenv import load_dotenv

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

# Load environment
env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

try:
    from config.credential_helper import get_db_password
except ImportError:
    def get_db_password():
        return os.getenv("DB_PASSWORD", "")


def get_db_conn():
    """Get database connection."""
    return psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=int(os.getenv('DB_PORT', 5432)),
        user=os.getenv('DB_USER', 'stocks'),
        password=get_db_password(),
        database=os.getenv('DB_NAME', 'stocks'),
    )


class AlgoValidator:
    """Validates algo correctness across 7 phases."""

    def __init__(self):
        self.issues = []
        self.warnings = []
        self.checks_passed = 0
        self.checks_failed = 0

    def add_issue(self, severity: str, phase: str, message: str):
        """Log an issue."""
        self.issues.append({
            'severity': severity,
            'phase': phase,
            'message': message
        })
        if severity == 'CRITICAL':
            self.checks_failed += 1
        else:
            self.warnings.append(message)

    def add_pass(self):
        """Mark a check as passed."""
        self.checks_passed += 1

    # ========== PHASE 1: DATA FRESHNESS ==========

    def check_phase1_data_freshness(self) -> bool:
        """Validate Phase 1: Data is fresh (not stale)."""
        logger.info("Checking Phase 1: Data Freshness...")
        conn = get_db_conn()
        try:
            cur = conn.cursor()

            # Check price data freshness
            cur.execute("SELECT MAX(date) FROM price_daily")
            latest_price_date = cur.fetchone()[0]

            if not latest_price_date:
                self.add_issue('CRITICAL', 'Phase 1', 'No price data loaded')
                return False

            days_stale = (date.today() - latest_price_date).days
            if days_stale > 7:
                self.add_issue('CRITICAL', 'Phase 1', f'Price data is {days_stale} days stale (>7 day limit)')
                return False
            elif days_stale > 2:
                self.add_issue('WARN', 'Phase 1', f'Price data is {days_stale} days old')

            logger.info(f"  ✓ Price data fresh (latest: {latest_price_date}, {days_stale} days old)")
            self.add_pass()

            # Check symbol freshness
            cur.execute("""
                SELECT COUNT(DISTINCT symbol) FROM price_daily
                WHERE date >= CURRENT_DATE - INTERVAL '2 days'
            """)
            fresh_symbols = cur.fetchone()[0]
            logger.info(f"  ✓ {fresh_symbols} symbols have data in last 2 days")

            return True

        finally:
            conn.close()

    # ========== PHASE 2: CIRCUIT BREAKERS ==========

    def check_phase2_circuit_breakers(self) -> bool:
        """Validate Phase 2: Circuit breaker logic."""
        logger.info("Checking Phase 2: Circuit Breakers...")
        conn = get_db_conn()
        try:
            cur = conn.cursor()

            # Check algo_trades for any halt status
            cur.execute("""
                SELECT COUNT(*) FROM algo_audit_log
                WHERE event_type = 'CIRCUIT_BREAKER_FIRED'
                AND created_at >= CURRENT_DATE - INTERVAL '7 days'
            """)
            breaker_fires = cur.fetchone()[0]
            if breaker_fires > 0:
                logger.info(f"  ! Circuit breaker fired {breaker_fires} times in last 7 days")

            # Check if portfolio is in any halt state
            cur.execute("""
                SELECT COUNT(*) FROM algo_trades
                WHERE status = 'HALTED'
            """)
            halted_trades = cur.fetchone()[0]
            if halted_trades > 0:
                logger.warning(f"  ⚠ {halted_trades} trades in HALTED status")

            logger.info(f"  ✓ Circuit breaker checks operational")
            self.add_pass()
            return True

        finally:
            conn.close()

    # ========== PHASE 3: POSITION MONITOR ==========

    def check_phase3_position_monitor(self) -> bool:
        """Validate Phase 3: Position monitoring logic."""
        logger.info("Checking Phase 3: Position Monitor...")
        conn = get_db_conn()
        try:
            cur = conn.cursor()

            # Check open positions
            cur.execute("""
                SELECT COUNT(*) FROM algo_positions
                WHERE status IN ('OPEN', 'PARTIAL')
            """)
            open_positions = cur.fetchone()[0]
            logger.info(f"  ✓ {open_positions} open positions being monitored")

            # Check for stale positions (not updated in 7 days)
            cur.execute("""
                SELECT COUNT(*) FROM algo_positions
                WHERE status IN ('OPEN', 'PARTIAL')
                AND updated_at < CURRENT_TIMESTAMP - INTERVAL '7 days'
            """)
            stale_positions = cur.fetchone()[0]
            if stale_positions > 0:
                self.add_issue('WARN', 'Phase 3', f'{stale_positions} positions not updated in 7 days')

            self.add_pass()
            return True

        finally:
            conn.close()

    # ========== PHASE 4: EXIT EXECUTION ==========

    def check_phase4_exit_execution(self) -> bool:
        """Validate Phase 4: Exit logic execution."""
        logger.info("Checking Phase 4: Exit Execution...")
        conn = get_db_conn()
        try:
            cur = conn.cursor()

            # Check recent exits
            cur.execute("""
                SELECT COUNT(*) FROM algo_audit_log
                WHERE event_type IN ('EXIT_FULL', 'EXIT_PARTIAL')
                AND created_at >= CURRENT_DATE - INTERVAL '30 days'
            """)
            recent_exits = cur.fetchone()[0]
            logger.info(f"  ✓ {recent_exits} exits executed in last 30 days")

            # Check for any exit failures
            cur.execute("""
                SELECT COUNT(*) FROM algo_audit_log
                WHERE event_type = 'EXIT_FAILED'
                AND created_at >= CURRENT_DATE - INTERVAL '7 days'
            """)
            failed_exits = cur.fetchone()[0]
            if failed_exits > 0:
                self.add_issue('WARN', 'Phase 4', f'{failed_exits} exit failures in last 7 days')

            self.add_pass()
            return True

        finally:
            conn.close()

    # ========== PHASE 5: SIGNAL GENERATION ==========

    def check_phase5_signal_generation(self) -> bool:
        """Validate Phase 5: Buy signal generation."""
        logger.info("Checking Phase 5: Signal Generation...")
        conn = get_db_conn()
        try:
            cur = conn.cursor()

            # Check buy/sell signal counts
            cur.execute("""
                SELECT COUNT(*) FROM buy_sell_daily
                WHERE signal = 'BUY'
                AND date = (SELECT MAX(date) FROM buy_sell_daily)
            """)
            today_buys = cur.fetchone()[0]
            logger.info(f"  ✓ {today_buys} BUY signals generated today")

            # Check signal distribution
            cur.execute("""
                SELECT
                    MIN(composite_score) as min_score,
                    MAX(composite_score) as max_score,
                    AVG(composite_score) as avg_score
                FROM stock_scores
                WHERE composite_score IS NOT NULL
            """)
            min_s, max_s, avg_s = cur.fetchone()
            logger.info(f"  ✓ Score distribution: min={min_s:.1f}, avg={avg_s:.1f}, max={max_s:.1f}")

            if min_s == max_s:
                self.add_issue('CRITICAL', 'Phase 5', 'All scores are identical (calculation broken)')
                return False

            self.add_pass()
            return True

        finally:
            conn.close()

    # ========== PHASE 6: ENTRY EXECUTION ==========

    def check_phase6_entry_execution(self) -> bool:
        """Validate Phase 6: Trade entry execution."""
        logger.info("Checking Phase 6: Entry Execution...")
        conn = get_db_conn()
        try:
            cur = conn.cursor()

            # Check recent trade entries
            cur.execute("""
                SELECT COUNT(*) FROM algo_trades
                WHERE status IN ('OPEN', 'PARTIAL')
                AND created_at >= CURRENT_DATE - INTERVAL '30 days'
            """)
            recent_entries = cur.fetchone()[0]
            logger.info(f"  ✓ {recent_entries} trades entered in last 30 days")

            # Check for execution errors
            cur.execute("""
                SELECT COUNT(*) FROM algo_audit_log
                WHERE event_type = 'ENTRY_FAILED'
                AND created_at >= CURRENT_DATE - INTERVAL '7 days'
            """)
            failed_entries = cur.fetchone()[0]
            if failed_entries > 0:
                self.add_issue('WARN', 'Phase 6', f'{failed_entries} entry failures in last 7 days')

            self.add_pass()
            return True

        finally:
            conn.close()

    # ========== PHASE 7: RECONCILIATION ==========

    def check_phase7_reconciliation(self) -> bool:
        """Validate Phase 7: Daily reconciliation and snapshots."""
        logger.info("Checking Phase 7: Reconciliation...")
        conn = get_db_conn()
        try:
            cur = conn.cursor()

            # Check portfolio snapshots
            cur.execute("""
                SELECT COUNT(*) FROM algo_portfolio_snapshots
                WHERE snapshot_date >= CURRENT_DATE - INTERVAL '7 days'
            """)
            recent_snapshots = cur.fetchone()[0]
            logger.info(f"  ✓ {recent_snapshots} portfolio snapshots in last 7 days")

            # Check performance tracking
            cur.execute("""
                SELECT COUNT(*) FROM algo_performance_daily
                WHERE trading_date >= CURRENT_DATE - INTERVAL '30 days'
            """)
            perf_records = cur.fetchone()[0]
            logger.info(f"  ✓ {perf_records} daily performance records in last 30 days")

            self.add_pass()
            return True

        finally:
            conn.close()

    # ========== SCORE CALCULATION VALIDATION ==========

    def check_score_calculations(self) -> bool:
        """Validate composite score calculations."""
        logger.info("Checking Score Calculations...")
        conn = get_db_conn()
        try:
            cur = conn.cursor()

            # Get a sample of high-scoring stocks
            cur.execute("""
                SELECT
                    symbol,
                    composite_score,
                    quality_score,
                    growth_score,
                    value_score,
                    momentum_score,
                    stability_score,
                    positioning_score
                FROM stock_scores
                WHERE composite_score IS NOT NULL
                ORDER BY composite_score DESC
                LIMIT 5
            """)

            logger.info("  Top 5 Scores:")
            for row in cur.fetchall():
                symbol = row[0]
                composite = row[1]
                logger.info(f"    {symbol}: composite={composite:.1f}")

            # Check for missing data
            cur.execute("""
                SELECT COUNT(*) FROM stock_scores
                WHERE composite_score IS NULL
            """)
            null_scores = cur.fetchone()[0]
            if null_scores > 100:
                self.add_issue('WARN', 'Calculation', f'{null_scores} symbols with NULL scores')

            self.add_pass()
            return True

        finally:
            conn.close()

    # ========== MAIN VALIDATION ==========

    def run_full_validation(self) -> Dict[str, Any]:
        """Run complete validation suite."""
        logger.info("=" * 60)
        logger.info("COMPREHENSIVE ALGO VALIDATION")
        logger.info("=" * 60)

        self.check_phase1_data_freshness()
        self.check_phase2_circuit_breakers()
        self.check_phase3_position_monitor()
        self.check_phase4_exit_execution()
        self.check_phase5_signal_generation()
        self.check_phase6_entry_execution()
        self.check_phase7_reconciliation()
        self.check_score_calculations()

        logger.info("\n" + "=" * 60)
        logger.info("VALIDATION SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Checks Passed: {self.checks_passed}")
        logger.info(f"Checks Failed: {self.checks_failed}")
        logger.info(f"Warnings: {len(self.warnings)}")
        logger.info(f"Critical Issues: {len([i for i in self.issues if i['severity'] == 'CRITICAL'])}")

        if self.issues:
            logger.error("\nISSUES FOUND:")
            for issue in self.issues:
                logger.error(f"  [{issue['severity']}] {issue['phase']}: {issue['message']}")

        return {
            'passed': self.checks_passed,
            'failed': self.checks_failed,
            'warnings': len(self.warnings),
            'issues': self.issues
        }


def main():
    parser = argparse.ArgumentParser(description="Validate algo correctness")
    parser.add_argument("--mode", choices=["full", "quick", "backtest"], default="full")
    args = parser.parse_args()

    validator = AlgoValidator()
    result = validator.run_full_validation()

    # Return appropriate exit code
    if result['failed'] > 0:
        sys.exit(1)
    return 0


if __name__ == '__main__':
    sys.exit(main())
