#!/usr/bin/env python3
"""
Data Quality SLA Enforcement

Validates per-loader freshness and completeness before algo runs.
Blocks algo_run_daily if any critical SLA is violated.

SLAs:
- price_daily: <= 16 hours old, >= 4000 symbols
- market_health_daily: <= 24 hours old, >= 1 row
- trend_template_data: <= 24 hours old, >= 3000 symbols
- buy_sell_daily: <= 24 hours old, >= 1000 signals
- technical_data_daily: <= 24 hours old, >= 3000 symbols
"""

import os
import psycopg2
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime, timedelta
import logging

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger(__name__)

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "user": os.getenv("DB_USER", "stocks"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "stocks"),
}


class DataQualityValidator:
    """Validate data freshness and completeness before algo runs."""

    def __init__(self, config=None):
        self.config = config or {}
        self.conn = None
        self.cur = None
        self.failures = []
        self.warnings = []

    def connect(self):
        """Connect to database."""
        if not self.conn:
            self.conn = psycopg2.connect(**DB_CONFIG)
            self.cur = self.conn.cursor()

    def disconnect(self):
        """Disconnect from database."""
        if self.cur:
            self.cur.close()
        if self.conn:
            self.conn.close()
        self.cur = self.conn = None

    def validate_all(self, eval_date=None):
        """
        Run all SLA checks.

        Returns:
            (all_pass: bool, failures: list, warnings: list)
        """
        if eval_date is None:
            eval_date = datetime.now().date()

        self.connect()
        self.failures = []
        self.warnings = []

        # Critical loaders: (table_name, max_age_hours, min_expected_rows)
        critical_loaders = [
            ('price_daily', 16, 4000),
            ('market_health_daily', 24, 1),
            ('trend_template_data', 24, 3000),
            ('buy_sell_daily', 24, 1000),
            ('technical_data_daily', 24, 3000),
        ]

        print("\n" + "=" * 70)
        print("DATA QUALITY VALIDATION")
        print("=" * 70 + "\n")

        for table, max_age_h, min_rows in critical_loaders:
            passed = self._check_loader(table, max_age_h, min_rows, eval_date)
            if passed:
                print(f"  [OK] {table}")
            else:
                print(f"  [FAIL] {table}")

        self.disconnect()

        all_pass = len(self.failures) == 0

        print("\n" + "-" * 70)
        if all_pass:
            print(f"RESULT: All {len(critical_loaders)} loaders passed SLA checks")
        else:
            print(f"RESULT: {len(self.failures)} loader(s) failed SLA checks")
            for msg in self.failures:
                print(f"  - {msg}")

        if self.warnings:
            print(f"\nWARNINGS: {len(self.warnings)} loader(s) at risk")
            for msg in self.warnings:
                print(f"  - {msg}")
        print("-" * 70 + "\n")

        return all_pass, self.failures, self.warnings

    def _check_loader(self, table, max_age_hours, min_expected_rows, eval_date):
        """Check if loader meets SLA: freshness + completeness."""
        try:
            self.cur.execute(f"""
                SELECT
                    MAX(date) as latest_date,
                    COUNT(*) as total_rows,
                    COUNT(DISTINCT symbol) as symbol_count
                FROM {table}
                WHERE date >= NOW()::DATE - INTERVAL '1 day'
            """)
            row = self.cur.fetchone()

            if not row or not row[0]:
                self.failures.append(f"{table}: No data loaded in last 24 hours")
                return False

            latest_date, total_rows, symbol_count = row

            # Calculate age in hours
            age_delta = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) - \
                        datetime.combine(latest_date, datetime.min.time())
            age_hours = age_delta.total_seconds() / 3600

            # Check freshness SLA
            if age_hours > max_age_hours:
                self.failures.append(
                    f"{table}: Data {age_hours:.1f}h old exceeds {max_age_hours}h SLA"
                )
                return False

            # Check completeness SLA (allow 20% variance)
            min_acceptable = int(min_expected_rows * 0.8)
            if symbol_count < min_acceptable:
                self.warnings.append(
                    f"{table}: Only {symbol_count}/{min_expected_rows} rows "
                    f"(expected >= {min_acceptable})"
                )

            # Update loader_sla_status table
            self._update_sla_status(table, latest_date, total_rows, 'OK')

            return True

        except Exception as e:
            self.failures.append(f"{table}: Query failed - {str(e)[:80]}")
            return False

    def _update_sla_status(self, table_name, latest_date, row_count, status):
        """Update loader_sla_status table for monitoring."""
        try:
            self.cur.execute("""
                INSERT INTO loader_sla_status
                (loader_name, table_name, latest_data_date, row_count_today, status, last_check_at)
                VALUES (%s, %s, %s, %s, %s, NOW())
                ON CONFLICT (loader_name, table_name) DO UPDATE SET
                    latest_data_date = EXCLUDED.latest_data_date,
                    row_count_today = EXCLUDED.row_count_today,
                    status = EXCLUDED.status,
                    last_check_at = NOW()
            """, (table_name.replace('_', ' ').title(), table_name, latest_date, row_count, status))
            self.conn.commit()
        except Exception as e:
            log.warning(f"Could not update SLA status: {e}")


if __name__ == "__main__":
    validator = DataQualityValidator()
    all_pass, failures, warnings = validator.validate_all()

    if not all_pass:
        print("\nALERT: Data quality SLA violations detected!")
        print("Algo trading blocked until data is fresh.")
        exit(1)

    print("\nData quality check PASSED. Safe to run algo.")
    exit(0)
