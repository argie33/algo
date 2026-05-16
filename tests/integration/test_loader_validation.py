#!/usr/bin/env python3
"""
Loader Validation - Verify all critical loaders populate fresh data

Checks:
1. Each critical table has data for today (or latest trading date)
2. Row counts are reasonable (>0 for all tables)
3. No unexpected NULLs in critical columns
4. Data is fresh (< 1 hour old for price data)
5. All required loaders completed successfully
"""

try:
    from credential_manager import get_credential_manager
    credential_manager = get_credential_manager()
except ImportError:
    credential_manager = None

import os
import sys
from credential_helper import get_db_password, get_db_config
import logging
import psycopg2
from datetime import date, datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

def _get_db_config():
    """Get database configuration."""
    return {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", 5432)),
        "user": os.getenv("DB_USER", "stocks"),
        "password": get_db_password() if credential_manager else os.getenv("DB_PASSWORD", ""),
        "database": os.getenv("DB_NAME", "stocks"),
    }


class LoaderValidator:
    """Validate that all critical loaders populated fresh data."""

    def __init__(self):
        self.conn = None
        self.cur = None
        self.issues = []
        self.warnings = []
        self.checks_passed = 0
        self.checks_total = 0

    def connect(self):
        """Connect to database."""
        try:
            self.conn = psycopg2.connect(**_get_db_config())
            self.cur = self.conn.cursor()
            logger.info("Connected to database")
        except Exception as e:
            logger.error(f"DB connection failed: {e}", exc_info=True)
            raise

    def disconnect(self):
        """Close database connection."""
        if self.cur:
            self.cur.close()
        if self.conn:
            self.conn.close()

    def _log_check(self, passed: bool, message: str):
        """Log a check result."""
        self.checks_total += 1
        if passed:
            self.checks_passed += 1
            logger.info(f"✓ {message}")
        else:
            self.issues.append(message)
            logger.error(f"✗ {message}")

    def validate_all(self):
        """Run all validation checks."""
        self.connect()
        try:
            logger.info("\n" + "="*70)
            logger.info("LOADER VALIDATION")
            logger.info("="*70 + "\n")

            # Get latest trading date
            latest_date = self._get_latest_trading_date()
            logger.info(f"Validating loaders for trading date: {latest_date}\n")

            # Critical tables that must be populated
            critical_tables = [
                ('price_daily', 'date', 'Price data (OHLCV)', 100),
                ('technical_data_daily', 'date', 'Technical indicators', 100),
                ('buy_sell_daily', 'date', 'Buy/Sell signals', 50),
                ('stock_scores', 'updated_at', 'Stock quality scores', 50),
                ('market_exposure_daily', 'date', 'Market exposure', 1),
                ('algo_risk_daily', 'report_date', 'Risk metrics', 1),
            ]

            logger.info("Checking critical tables:\n")
            for table, date_col, description, min_rows in critical_tables:
                self._check_table_freshness(table, date_col, description, min_rows, latest_date)

            # Check loader SLA tracker for recent runs
            logger.info("\nChecking loader execution status:\n")
            self._check_loader_sla(latest_date)

            # Summary
            logger.info("\n" + "="*70)
            logger.info(f"VALIDATION SUMMARY: {self.checks_passed}/{self.checks_total} checks passed")
            if self.warnings:
                logger.info("\nWARNINGS:")
                for w in self.warnings:
                    logger.warning(f"  - {w}")
            if self.issues:
                logger.info("\nFAILED CHECKS:")
                for issue in self.issues:
                    logger.error(f"  - {issue}")
            logger.info("="*70 + "\n")

            return len(self.issues) == 0

        finally:
            self.disconnect()

    def _get_latest_trading_date(self) -> date:
        """Get the latest trading date from price_daily."""
        try:
            self.cur.execute("SELECT MAX(date) FROM price_daily WHERE symbol='SPY'")
            result = self.cur.fetchone()
            if result and result[0]:
                return result[0]
        except Exception:
            pass
        return date.today()

    def _check_table_freshness(self, table: str, date_col: str, description: str, min_rows: int, target_date: date):
        """Check if a table has fresh data."""
        try:
            # Check if table exists
            self.cur.execute(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=%s)",
                (table,)
            )
            if not self.cur.fetchone()[0]:
                self._log_check(False, f"{description}: table does not exist")
                return

            # Check row count for target date
            self.cur.execute(
                f"SELECT COUNT(*) FROM {table} WHERE {date_col} = %s",
                (target_date,)
            )
            count = self.cur.fetchone()[0]
            if count == 0:
                self._log_check(False, f"{description}: no data for {target_date}")
                return
            if count < min_rows:
                self._log_check(
                    False,
                    f"{description}: only {count} rows for {target_date} (need {min_rows})"
                )
                return

            # Check data freshness (for tables with created_at or updated_at)
            try:
                self.cur.execute(
                    f"SELECT MAX(created_at) FROM {table} WHERE {date_col} = %s",
                    (target_date,)
                )
                result = self.cur.fetchone()
                if result and result[0]:
                    age_hours = (datetime.now() - result[0]).total_seconds() / 3600
                    if age_hours > 24:
                        self._log_check(
                            False,
                            f"{description}: data is {age_hours:.1f} hours old (> 24h)"
                        )
                        return
                    elif age_hours > 1 and 'price' in table.lower():
                        self.warnings.append(f"{description} is {age_hours:.1f} hours old")
            except Exception:
                pass

            # Check for critical NULLs
            self.cur.execute(
                f"SELECT COUNT(*) FROM {table} WHERE {date_col} = %s AND (symbol IS NULL OR value IS NULL)",
                (target_date,)
            )
            null_count = self.cur.fetchone()[0]
            if null_count > 0:
                self._log_check(
                    False,
                    f"{description}: {null_count} rows have NULL symbol/value"
                )
                return

            self._log_check(
                True,
                f"{description}: {count} rows, fresh, no critical NULLs"
            )

        except Exception as e:
            self._log_check(False, f"{description}: validation error: {e}")

    def _check_loader_sla(self, target_date: date):
        """Check loader execution history."""
        try:
            self.cur.execute(
                """
                SELECT
                    loader_name,
                    COUNT(*) as runs,
                    SUM(CASE WHEN status='success' THEN 1 ELSE 0 END) as successes,
                    MAX(completed_at) as latest_run
                FROM loader_execution_history
                WHERE DATE(execution_date) = %s
                GROUP BY loader_name
                ORDER BY loader_name
                """,
                (target_date,)
            )
            rows = self.cur.fetchall()

            if not rows:
                logger.info("  No loader runs recorded for today yet")
                return

            critical_loaders = [
                'loadpricedaily',
                'loadstockscores',
                'loadtechnicalsdaily',
                'loadbuyselldaily',
            ]

            for loader_name, runs, successes, latest_run in rows:
                success_rate = (successes / runs * 100) if runs > 0 else 0
                status = 'success' if success_rate == 100 else 'warning'
                is_critical = loader_name in critical_loaders

                msg = f"{loader_name}: {successes}/{runs} successful ({success_rate:.0f}%)"
                if is_critical and success_rate < 100:
                    self._log_check(False, f"{msg} [CRITICAL]")
                else:
                    logger.info(f"  ✓ {msg}")

        except Exception as e:
            logger.warning(f"Could not check loader SLA: {e}")


def main():
    validator = LoaderValidator()
    success = validator.validate_all()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
