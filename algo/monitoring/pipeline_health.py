#!/usr/bin/env python3

import logging
import os
from dataclasses import dataclass, field
from datetime import date as _date
from datetime import datetime
from enum import Enum
from typing import Any

import psycopg2

from utils.db import DatabaseContext, assert_safe_column, assert_safe_table
from utils.infrastructure import EASTERN_TZ

logger = logging.getLogger(__name__)


class HealthStatus(str, Enum):
    HEALTHY = "HEALTHY"
    STALE = "STALE"  # Data older than SLA
    VERY_STALE = "VERY_STALE"  # Data > 2x SLA old
    MISSING = "MISSING"  # Table empty
    ERROR = "ERROR"  # Query failed


@dataclass
class TableHealth:
    """Health status for a single table."""

    table_name: str
    status: HealthStatus
    row_count: int = 0
    latest_date: _date | None = None
    age_days: int = 0
    sla_days: int = 7
    last_checked: datetime = field(default_factory=datetime.now)
    error_message: str | None = None

    @property
    def is_healthy(self) -> bool:
        return self.status == HealthStatus.HEALTHY

    @property
    def is_critical(self) -> bool:
        """Check if table is critical for algo execution.

        buy_sell_daily and stock_scores are excluded - they are orchestrator OUTPUTS
        (written by Phase 5/6), not upstream inputs. Treating them as critical halts
        Phase 1 before Phase 5/6 can populate them (circular dependency).

        economic_data is excluded - it stores FRED macro series with no pipeline loader;
        algo_market_exposure.py handles missing rows with safe defaults.
        """
        critical_tables = {
            "stock_symbols",
            "price_daily",
            "market_health_daily",
        }
        return self.table_name in critical_tables

    def to_dict(self) -> dict[str, Any]:
        return {
            "table": self.table_name,
            "status": self.status.value,
            "rows": self.row_count,
            "latest_date": self.latest_date.isoformat() if self.latest_date else None,
            "age_days": self.age_days,
            "sla_days": self.sla_days,
            "is_healthy": self.is_healthy,
            "is_critical": self.is_critical,
            "error": self.error_message,
        }


@dataclass
class PipelineStatus:
    """Overall pipeline health status."""

    timestamp: datetime = field(default_factory=datetime.now)
    tables: dict[str, TableHealth] = field(default_factory=dict)
    is_healthy: bool = True
    critical_alerts: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def healthy_count(self) -> int:
        return sum(1 for t in self.tables.values() if t.is_healthy)

    @property
    def total_count(self) -> int:
        return len(self.tables)

    @property
    def coverage_pct(self) -> float:
        if not self.tables:
            return 0.0
        return (self.healthy_count / self.total_count) * 100

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "is_healthy": self.is_healthy,
            "healthy_count": self.healthy_count,
            "total_count": self.total_count,
            "coverage_pct": round(self.coverage_pct, 1),
            "critical_alerts": self.critical_alerts,
            "warnings": self.warnings,
            "tables": {name: t.to_dict() for name, t in self.tables.items()},
        }


class PipelineHealth:
    """Monitor and report on data pipeline health."""

    # Define critical tables and their SLA requirements.
    # market_health_daily and price_daily use sla_days=5 so that a 3-day holiday
    # weekend (e.g. Memorial Day Friday -> Tuesday = 4 calendar days) or a 4-day
    # Thanksgiving break (Wednesday -> Monday = 5 days) does not trigger a VERY_STALE
    # critical halt in Phase 1. Phase 1's explicit staleness check uses trading-day-
    # aware comparison; PipelineHealth is a secondary check and should not over-block.
    CRITICAL_TABLES: dict[str, dict[str, str | int]] = {
        "stock_symbols": {"date_column": "created_at", "sla_days": 30},
        "price_daily": {"date_column": "date", "sla_days": 5},
        "buy_sell_daily": {"date_column": "date", "sla_days": 5},
        "stock_scores": {"date_column": "updated_at", "sla_days": 5},
        "economic_data": {"date_column": "date", "sla_days": 7},
        "market_health_daily": {"date_column": "date", "sla_days": 5},
        "analyst_sentiment_analysis": {"date_column": "updated_at", "sla_days": 7},
        "earnings_calendar": {"date_column": "created_at", "sla_days": 30},
    }

    def check_table_health(self, cur: Any, table_name: str, date_column: str | None, sla_days: int) -> TableHealth:
        health = TableHealth(table_name=table_name, status=HealthStatus.ERROR, sla_days=sla_days)

        try:
            safe_table = assert_safe_table(table_name)

            # Use pg_class.reltuples for O(1) approximate row count instead of
            # COUNT(*) full scan. reltuples is updated by ANALYZE and is accurate
            # enough to detect empty vs populated tables without blocking I/O.
            cur.execute(
                "SELECT GREATEST(reltuples, 0)::BIGINT FROM pg_class WHERE relname = %s LIMIT 1",
                (table_name,),
            )
            result = cur.fetchone()
            if result is None:
                logger.error(f"Pipeline health check failed for {table_name}: query returned None")
                health.status = HealthStatus.ERROR
                health.error_message = f"Failed to get row count for {table_name}"
                return health
            # DictCursor names the GREATEST() expression result as "greatest"
            if isinstance(result, dict):
                greatest_val = result.get("greatest")
                cnt: int = int(greatest_val) if greatest_val is not None else int(result.get("cnt") or 0)
                health.row_count = cnt
            else:
                health.row_count = int(result[0])

            if health.row_count == 0:
                health.status = HealthStatus.MISSING
                health.error_message = "Table is empty"
                return health

            if date_column is None:
                # No usable date column was found for this table (see _infer_date_column) -
                # age cannot be determined. Report HEALTHY based on row count alone rather
                # than guessing a column name and risking an UndefinedColumn error, which
                # would abort the shared transaction and poison every subsequent table check
                # in this batch (see get_pipeline_status).
                health.status = HealthStatus.HEALTHY
                health.error_message = "No date column available - age not checked"
                return health

            safe_date_col = assert_safe_column(date_column)

            # Use ORDER BY + LIMIT 1 instead of MAX() - forces an index scan and
            # avoids sequential scans when PostgreSQL statistics are stale (reltuples=0
            # on t4g.micro after bulk inserts). MAX() with stale stats can take 30s+.
            cur.execute(f"SELECT {safe_date_col}::DATE FROM {safe_table} ORDER BY {safe_date_col} DESC LIMIT 1")
            result = cur.fetchone()
            # DictCursor returns dict; support both dict and tuple indexing
            if isinstance(result, dict):
                latest_date = result.get(safe_date_col) or result.get("date")
            else:
                latest_date = result[0] if result else None

            if not latest_date:
                health.status = HealthStatus.MISSING
                health.error_message = f"No {date_column} values found"
                return health

            if isinstance(latest_date, datetime):
                latest_date = latest_date.date()

            health.latest_date = latest_date
            # Use ET date for age calculation (trading is ET-based)

            today_et = datetime.now(EASTERN_TZ).date()
            health.age_days = (today_et - latest_date).days

            # Determine status based on SLA
            if health.age_days > (sla_days * 2):
                health.status = HealthStatus.VERY_STALE
            elif health.age_days > sla_days:
                health.status = HealthStatus.STALE
            else:
                health.status = HealthStatus.HEALTHY

        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            health.status = HealthStatus.ERROR
            health.error_message = str(e)

        return health

    def update_loader_status_age_days(self) -> int:
        """Update age_days for all tables in data_loader_status.

        CRITICAL FIX (Session 289): age_days was NULL for 95% of tables.
        This calculates age in days from last_updated and persists to data_loader_status.

        Returns: count of rows updated
        """
        try:
            with DatabaseContext("write") as cur:
                # Calculate age_days for all rows where last_updated exists
                cur.execute("""
                    UPDATE data_loader_status
                    SET age_days = EXTRACT(DAY FROM NOW() - last_updated)::INTEGER
                    WHERE last_updated IS NOT NULL
                      AND (age_days IS NULL OR age_days != EXTRACT(DAY FROM NOW() - last_updated)::INTEGER)
                """)
                rows_updated = cur.rowcount
                logger.info(f"[LOADER_STATUS] Updated age_days for {rows_updated} tables")
                return rows_updated
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.error(f"[LOADER_STATUS] Failed to update age_days: {e}")
            return 0

    def get_pipeline_status(self) -> PipelineStatus:
        status = PipelineStatus()

        try:
            # CRITICAL: Update age_days BEFORE checking status so monitoring is current
            self.update_loader_status_age_days()

            with DatabaseContext("read") as cur:
                # Set statement timeout for health checks (fail fast)
                stmt_timeout_ms = int(os.getenv("DB_STATEMENT_TIMEOUT_MS", 30000))
                cur.execute("SET statement_timeout = %s", (f"{stmt_timeout_ms}ms",))

                # First: Check all critical tables (explicit configuration)
                for table_name, config in self.CRITICAL_TABLES.items():
                    try:
                        health = self.check_table_health(
                            cur,
                            table_name,
                            str(config["date_column"]),
                            int(config["sla_days"]),
                        )
                        status.tables[table_name] = health

                        # Alert on critical issues
                        if health.is_critical:
                            if health.status == HealthStatus.MISSING:
                                status.critical_alerts.append(
                                    f"CRITICAL: {table_name} is empty - no trades can execute"
                                )
                            elif health.status == HealthStatus.VERY_STALE:
                                status.critical_alerts.append(
                                    f"CRITICAL: {table_name} is very stale ({health.age_days} days old)"
                                )
                            elif health.status == HealthStatus.STALE:
                                status.warnings.append(f"WARNING: {table_name} is stale ({health.age_days} days old)")
                    except (ValueError, ZeroDivisionError, TypeError) as e:
                        logger.error(f"Error checking {table_name}: {e}")
                        status.tables[table_name] = TableHealth(
                            table_name=table_name,
                            status=HealthStatus.ERROR,
                            error_message=str(e),
                        )

                # Second: Check all other tables in data_loader_status with default SLA
                # CRITICAL FIX: Previously only 8 tables were monitored, leaving 86 tables
                # with NULL row_count and age_days. Now ALL tables are monitored.
                try:
                    # Use = ANY(...) instead of NOT IN for proper PostgreSQL array comparison
                    cur.execute(
                        """
                        SELECT DISTINCT table_name FROM data_loader_status
                        WHERE table_name != ALL(%s)
                        ORDER BY table_name
                        """,
                        (list(self.CRITICAL_TABLES.keys()),),
                    )
                    other_tables = [row[0] for row in cur.fetchall()]

                    # Default SLA for non-critical tables (7 days)
                    DEFAULT_SLA_DAYS = 7
                    DEFAULT_DATE_COLUMN = "updated_at"  # Most tables use updated_at

                    for table_name in other_tables:
                        try:
                            # Try to find a sensible date column for age calculation
                            # Most algo_* tables use created_at, updated_at, or date
                            date_column = self._infer_date_column(cur, table_name)
                            if date_column is None:
                                logger.warning(f"Could not infer date column for {table_name}, skipping age check")

                            health = self.check_table_health(
                                cur,
                                table_name,
                                date_column,
                                DEFAULT_SLA_DAYS,
                            )
                            status.tables[table_name] = health
                        except (ValueError, ZeroDivisionError, TypeError) as e:
                            logger.warning(f"Error checking secondary table {table_name}: {e}")
                            status.tables[table_name] = TableHealth(
                                table_name=table_name,
                                status=HealthStatus.ERROR,
                                error_message=str(e),
                            )
                except Exception as e:
                    logger.error(f"Error fetching secondary tables list: {e}")
                    # Continue anyway with just critical tables

        except (ValueError, ZeroDivisionError, TypeError) as e:
            logger.error(f"Cannot check pipeline status: {e}")
            status.is_healthy = False
            status.critical_alerts.append(f"Database connection failed: {e}")
            return status

        # Overall health determination
        has_critical_issues = any(not t.is_healthy and t.is_critical for t in status.tables.values())
        status.is_healthy = not has_critical_issues and len(status.critical_alerts) == 0

        return status

    def _infer_date_column(self, cur: Any, table_name: str) -> str | None:
        """Infer the date column for a table by checking column existence.

        Tries in order: date, updated_at, created_at, date_added.
        Returns None if no date column found.
        """
        try:
            safe_table = assert_safe_table(table_name)
            for col in ["date", "updated_at", "created_at", "date_added"]:
                safe_col = assert_safe_column(col)
                cur.execute(
                    f"SELECT 1 FROM information_schema.columns WHERE table_name = %s AND column_name = %s LIMIT 1",
                    (table_name, col),
                )
                if cur.fetchone():
                    return col
        except Exception as e:
            logger.debug(f"Error inferring date column for {table_name}: {e}")
        return None

    def log_health_check(self, status: PipelineStatus) -> None:
        """Log pipeline health to database for historical tracking."""
        try:
            with DatabaseContext("write") as cur:
                if status.tables:
                    insert_values = [
                        (
                            table_health.table_name,
                            table_health.status.value,
                            table_health.row_count,
                            table_health.latest_date,
                            table_health.age_days,
                        )
                        for table_health in status.tables.values()
                    ]
                    cur.executemany(
                        """
                        INSERT INTO data_loader_status
                        (table_name, status, row_count, latest_date, age_days, last_updated)
                        VALUES (%s, %s, %s, %s, %s, NOW())
                        ON CONFLICT (table_name)
                        DO UPDATE SET
                            status = EXCLUDED.status,
                            row_count = EXCLUDED.row_count,
                            latest_date = EXCLUDED.latest_date,
                            age_days = EXCLUDED.age_days,
                            last_updated = NOW()
                        """,
                        insert_values,
                    )
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.error(f"[LOGGING_FAILURE] Could not log health check: {e}")
            raise

    def assert_pipeline_ready(self) -> bool:
        """Check if pipeline is ready for trading.
        Raises exception if critical data is missing/stale.
        """
        status = self.get_pipeline_status()

        if status.critical_alerts:
            error_msg = "Pipeline not ready for trading:\n" + "\n".join(status.critical_alerts)
            logger.error(error_msg)
            raise RuntimeError(error_msg)

        return True


if __name__ == "__main__":
    import json

    health = PipelineHealth()
    status = health.get_pipeline_status()
    logger.info(json.dumps(status.to_dict(), indent=2, default=str))
