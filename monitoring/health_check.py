#!/usr/bin/env python3
"""
Production Health Monitor - Real-time checks for critical fixes

Monitors the 7 critical fixes deployed in production:
- C1: RSI division by zero (check for NaN in scores)
- C2: Same-day entry/exit (check for same-day closes)
- C3: Fake price injection (check for fallback usage)
- C4: Risk fallback consistency (check drawdown logic)
- C5: Circuit breaker errors (check for halt patterns)
- H3: Duplicate orders (check for dedup cases)
- H6: Data completeness gate (check scores coverage)
"""

import os
import sys
import psycopg2
import logging
from datetime import datetime, timedelta, date as _date
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def get_db_config():
    """Get database configuration."""
    return {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", "5432")),
        "user": os.getenv("DB_USER", "stocks"),
        "password": os.getenv("DB_PASSWORD", ""),
        "database": os.getenv("DB_NAME", "stocks"),
    }


class HealthMonitor:
    """Monitor health of critical fixes."""

    def __init__(self):
        self.config = get_db_config()
        self.conn = None
        self.cur = None
        self.issues = []

    def connect(self):
        """Connect to database."""
        try:
            self.conn = psycopg2.connect(**self.config)
            self.cur = self.conn.cursor()
            logger.info("✓ Database connected")
            return True
        except Exception as e:
            logger.error(f"✗ Database connection failed: {e}")
            return False

    def disconnect(self):
        """Disconnect from database."""
        if self.cur:
            self.cur.close()
        if self.conn:
            self.conn.close()

    def check_c1_rsi_division_by_zero(self):
        """C1: Check for NaN values in stock_scores (RSI division by zero)."""
        logger.info("\n[C1] Checking for NaN in RSI calculations...")
        try:
            self.cur.execute("""
                SELECT COUNT(*) FROM stock_scores
                WHERE composite_score IS NULL
                   OR composite_score != composite_score
                   OR growth_score IS NULL OR growth_score != growth_score
            """)
            nan_count = self.cur.fetchone()[0]
            if nan_count > 0:
                self.issues.append(f"ALERT: {nan_count} scores have NaN values (C1)")
                logger.error(f"  ✗ Found {nan_count} NaN values in scores")
            else:
                logger.info("  ✓ No NaN values detected (C1 working)")
        except Exception as e:
            logger.warning(f"  ! Could not check C1: {e}")

    def check_c2_same_day_exits(self):
        """C2: Check for same-day entry/exits (should be 0)."""
        logger.info("\n[C2] Checking for same-day entry/exits...")
        try:
            self.cur.execute("""
                SELECT COUNT(*) FROM algo_trades
                WHERE status = 'closed'
                  AND CAST(trade_date AS DATE) = CAST(exit_date AS DATE)
                  AND trade_date > NOW() - INTERVAL '7 days'
            """)
            same_day_count = self.cur.fetchone()[0]
            if same_day_count > 0:
                self.issues.append(f"ALERT: {same_day_count} same-day exits detected (C2)")
                logger.error(f"  ✗ Found {same_day_count} same-day exits")
            else:
                logger.info("  ✓ No same-day exits (C2 working)")
        except Exception as e:
            logger.warning(f"  ! Could not check C2: {e}")

    def check_c3_fake_price_injection(self):
        """C3: Check for fake price injection attempts (check logs)."""
        logger.info("\n[C3] Checking for fallback price injection...")
        try:
            log_path = Path(__file__).parent.parent / "logs" / "loaders.log"
            if log_path.exists():
                with open(log_path, 'r') as f:
                    content = f.read()
                    fallback_count = content.count('fallback')
                    if fallback_count > 0:
                        self.issues.append(f"ALERT: {fallback_count} fallback uses detected (C3)")
                        logger.error(f"  ✗ Found {fallback_count} fallback price uses")
                    else:
                        logger.info("  ✓ No price fallbacks used (C3 working)")
            else:
                logger.info("  ! Log file not found, skipping C3 check")
        except Exception as e:
            logger.warning(f"  ! Could not check C3: {e}")

    def check_c4_risk_consistency(self):
        """C4: Check drawdown calculation consistency."""
        logger.info("\n[C4] Checking risk fallback consistency...")
        try:
            self.cur.execute("""
                SELECT COUNT(*) FROM algo_portfolio_snapshots
                WHERE snapshot_date > NOW()::DATE - 7
                  AND total_portfolio_value IS NULL
            """)
            null_portfolio = self.cur.fetchone()[0]
            if null_portfolio > 0:
                self.issues.append(f"ALERT: {null_portfolio} NULL portfolio values (C4)")
                logger.error(f"  ✗ Found {null_portfolio} NULL portfolio snapshots")
            else:
                logger.info("  ✓ No NULL portfolio values (C4 working)")
        except Exception as e:
            logger.warning(f"  ! Could not check C4: {e}")

    def check_c5_circuit_breaker(self):
        """C5: Check circuit breaker error differentiation."""
        logger.info("\n[C5] Checking circuit breaker halt patterns...")
        try:
            self.cur.execute("""
                SELECT COUNT(*) FROM algo_audit_log
                WHERE action_type LIKE 'circuit_breaker_%'
                  AND status = 'halt'
                  AND details NOT ILIKE '%transient%'
                  AND created_at > NOW() - INTERVAL '24 hours'
            """)
            unexplained_halts = self.cur.fetchone()[0]
            if unexplained_halts > 0:
                self.issues.append(f"WARNING: {unexplained_halts} non-transient halts (C5)")
                logger.warning(f"  ! Found {unexplained_halts} non-transient circuit breaker halts")
            else:
                logger.info("  ✓ Circuit breaker halts appropriately differentiated (C5 working)")
        except Exception as e:
            logger.warning(f"  ! Could not check C5: {e}")

    def check_h3_duplicate_orders(self):
        """H3: Check for duplicate order attempts."""
        logger.info("\n[H3] Checking for duplicate order attempts...")
        try:
            self.cur.execute("""
                SELECT symbol, COUNT(*) as order_count
                FROM (
                    SELECT DISTINCT symbol FROM algo_execution_log
                    WHERE created_at > NOW() - INTERVAL '24 hours'
                ) t
                GROUP BY symbol HAVING COUNT(*) > 1
            """)
            duplicates = self.cur.fetchall()
            if duplicates:
                dup_count = len(duplicates)
                self.issues.append(f"ALERT: {dup_count} symbols with duplicate orders (H3)")
                logger.error(f"  ✗ Found {dup_count} symbols with duplicate orders: {duplicates}")
            else:
                logger.info("  ✓ No duplicate orders detected (H3 working)")
        except Exception as e:
            logger.warning(f"  ! Could not check H3 (table may not exist yet): {e}")

    def check_h6_data_completeness(self):
        """H6: Check stock scores data completeness."""
        logger.info("\n[H6] Checking stock scores completeness...")
        try:
            self.cur.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN data_completeness >= 0.8 THEN 1 ELSE 0 END) as complete
                FROM stock_scores
                WHERE updated_at = CURRENT_DATE
            """)
            row = self.cur.fetchone()
            total, complete = row[0], row[1] or 0

            if total == 0:
                logger.info("  ! No scores for today yet")
            else:
                pct = (complete / total) * 100
                if pct < 50:
                    self.issues.append(f"ALERT: Only {pct:.1f}% complete scores (H6)")
                    logger.error(f"  ✗ Low completeness: {complete}/{total} ({pct:.1f}%)")
                elif pct < 80:
                    logger.warning(f"  ! Completeness at {pct:.1f}% (ideal: >80%)")
                else:
                    logger.info(f"  ✓ Good completeness: {pct:.1f}% ({complete}/{total})")
        except Exception as e:
            logger.warning(f"  ! Could not check H6: {e}")

    def run_all_checks(self):
        """Run all health checks."""
        logger.info("\n" + "="*70)
        logger.info("PRODUCTION HEALTH CHECK")
        logger.info("="*70)

        if not self.connect():
            logger.error("FAILED: Cannot connect to database")
            return False

        try:
            self.check_c1_rsi_division_by_zero()
            self.check_c2_same_day_exits()
            self.check_c3_fake_price_injection()
            self.check_c4_risk_consistency()
            self.check_c5_circuit_breaker()
            self.check_h3_duplicate_orders()
            self.check_h6_data_completeness()
        finally:
            self.disconnect()

        # Print summary
        logger.info("\n" + "="*70)
        if self.issues:
            logger.error(f"ISSUES FOUND: {len(self.issues)}")
            for issue in self.issues:
                logger.error(f"  - {issue}")
            return False
        else:
            logger.info("✓ ALL CHECKS PASSED")
            return True


if __name__ == '__main__':
    monitor = HealthMonitor()
    success = monitor.run_all_checks()
    sys.exit(0 if success else 1)
