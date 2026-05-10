#!/usr/bin/env python3
"""
Loader SLA Tracker - Track loader success/failure and data freshness

Used by:
1. Individual loaders (log their results)
2. data_quality_validator.py (record daily SLA)
3. algo_orchestrator.py (check if data is fresh before trading)

Provides visibility into:
- Which loaders ran today and succeeded/failed
- What data is fresh vs stale
- Loader success rate over time
"""

import logging
import psycopg2
from datetime import datetime, date
from typing import Optional, Dict, List
import os
from pathlib import Path
from dotenv import load_dotenv

from credential_manager import get_credential_manager

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

log = logging.getLogger(__name__)
credential_manager = get_credential_manager()


class LoaderSLATracker:
    """Track loader execution and SLA status."""

    def __init__(self):
        self.conn = None

    def connect(self):
        """Connect to database."""
        if not self.conn:
            self.conn = psycopg2.connect(
                host=os.getenv("DB_HOST", "localhost"),
                port=int(os.getenv("DB_PORT", 5432)),
                user=os.getenv("DB_USER", "stocks"),
                password=credential_manager.get_db_credentials()["password"],
                database=os.getenv("DB_NAME", "stocks"),
            )

    def disconnect(self):
        """Disconnect from database."""
        if self.conn:
            self.conn.close()
            self.conn = None

    def record_execution(
        self,
        loader_name: str,
        table_name: str,
        execution_date: date,
        status: str,  # 'SUCCESS', 'PARTIAL', 'FAILED'
        rows_attempted: int,
        rows_succeeded: int,
        rows_rejected: int,
        started_at: datetime,
        completed_at: datetime,
        error_message: Optional[str] = None,
        data_source: Optional[str] = None,
    ) -> bool:
        """
        Record a loader execution attempt.

        Args:
            loader_name: e.g., "Price Daily"
            table_name: e.g., "price_daily"
            execution_date: What date was being loaded
            status: 'SUCCESS', 'PARTIAL', 'FAILED'
            rows_attempted: How many rows attempted
            rows_succeeded: How many rows inserted
            rows_rejected: How many failed quality checks
            started_at: When execution started
            completed_at: When execution finished
            error_message: If failed, the error message
            data_source: e.g., 'yfinance', 'alpaca'

        Returns:
            True if recorded successfully
        """
        try:
            self.connect()

            duration_seconds = (completed_at - started_at).total_seconds()

            with self.conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO loader_execution_history
                    (loader_name, table_name, execution_date, status,
                     rows_attempted, rows_succeeded, rows_rejected,
                     error_message, started_at, completed_at, duration_seconds,
                     data_source)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    loader_name,
                    table_name,
                    execution_date,
                    status,
                    rows_attempted,
                    rows_succeeded,
                    rows_rejected,
                    error_message,
                    started_at,
                    completed_at,
                    duration_seconds,
                    data_source,
                ))
                self.conn.commit()
                log.info(f"Recorded: {loader_name} {status} ({rows_succeeded}/{rows_attempted} rows)")
                return True

        except Exception as e:
            log.error(f"Failed to record execution: {e}")
            return False

    def update_sla_status(
        self,
        loader_name: str,
        table_name: str,
        latest_data_date: Optional[date],
        row_count_today: int,
        status: str,  # 'OK', 'WARN', 'ERROR'
        error_message: Optional[str] = None,
    ) -> bool:
        """
        Update current SLA status for a loader.

        Used by data_quality_validator.py after checking freshness/completeness.
        """
        try:
            self.connect()

            with self.conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO loader_sla_status
                    (loader_name, table_name, latest_data_date, row_count_today, status, error_message, last_check_at)
                    VALUES (%s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (loader_name, table_name) DO UPDATE SET
                        latest_data_date = EXCLUDED.latest_data_date,
                        row_count_today = EXCLUDED.row_count_today,
                        status = EXCLUDED.status,
                        error_message = EXCLUDED.error_message,
                        last_check_at = NOW()
                """, (
                    loader_name,
                    table_name,
                    latest_data_date,
                    row_count_today,
                    status,
                    error_message,
                ))
                self.conn.commit()
                return True

        except Exception as e:
            log.error(f"Failed to update SLA status: {e}")
            return False

    def get_today_status(self) -> Dict[str, dict]:
        """
        Get SLA status for all loaders today.

        Returns:
            {
                "price_daily": {"status": "OK", "row_count": 4000, ...},
                "buy_sell_daily": {"status": "ERROR", "error": "No data loaded"},
                ...
            }
        """
        try:
            self.connect()

            with self.conn.cursor() as cur:
                cur.execute("""
                    SELECT loader_name, table_name, status, row_count_today, error_message
                    FROM loader_sla_status
                    WHERE DATE(last_check_at) = CURRENT_DATE
                    ORDER BY loader_name
                """)

                result = {}
                for loader_name, table_name, status, row_count, error_msg in cur.fetchall():
                    result[table_name] = {
                        'loader_name': loader_name,
                        'table_name': table_name,
                        'status': status,
                        'row_count': row_count,
                        'error_message': error_msg,
                    }
                return result

        except Exception as e:
            log.error(f"Failed to get status: {e}")
            return {}

    def check_critical_loaders(self) -> tuple[bool, List[str]]:
        """
        Check if all critical loaders have fresh data.

        Critical loaders (must have data):
        - price_daily
        - buy_sell_daily

        Returns:
            (all_critical_ok, list_of_failures)
        """
        critical_tables = ['price_daily', 'buy_sell_daily']
        failures = []

        try:
            self.connect()

            with self.conn.cursor() as cur:
                for table_name in critical_tables:
                    cur.execute("""
                        SELECT status, error_message
                        FROM loader_sla_status
                        WHERE table_name = %s
                        AND last_check_at >= NOW() - INTERVAL '1 day'
                    """, (table_name,))

                    row = cur.fetchone()
                    if not row:
                        failures.append(f"{table_name}: Never loaded")
                        continue

                    status, error = row
                    if status != 'OK':
                        failures.append(f"{table_name}: {status} ({error})")

            return len(failures) == 0, failures

        except Exception as e:
            log.error(f"Critical check failed: {e}")
            return False, [f"Database error: {e}"]

    def get_success_rate_7d(self, loader_name: str) -> float:
        """Get loader success rate over last 7 days (0-100)."""
        try:
            self.connect()

            with self.conn.cursor() as cur:
                cur.execute("""
                    SELECT
                        COUNT(*) as total,
                        SUM(CASE WHEN status = 'SUCCESS' THEN 1 ELSE 0 END) as successful
                    FROM loader_execution_history
                    WHERE loader_name = %s
                    AND created_at >= NOW() - INTERVAL '7 days'
                """, (loader_name,))

                row = cur.fetchone()
                if not row or row[0] == 0:
                    return 0.0

                total, successful = row
                return 100.0 * successful / total

        except Exception as e:
            log.error(f"Failed to get success rate: {e}")
            return 0.0


# Singleton instance
_tracker = None


def get_tracker() -> LoaderSLATracker:
    """Get the singleton SLA tracker."""
    global _tracker
    if _tracker is None:
        _tracker = LoaderSLATracker()
    return _tracker
