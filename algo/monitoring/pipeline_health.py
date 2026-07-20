#!/usr/bin/env python3

import logging
import os
from dataclasses import dataclass, field
from datetime import date as _date
from datetime import datetime
from enum import Enum
from typing import Any

import psycopg2

from algo.infrastructure.market_calendar import MarketCalendar
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

        buy_sell_daily and technical_data_daily ARE upstream loader-pipeline outputs
        (EOD Step Functions pipeline, loaders/load_buy_sell_daily.py and
        loaders/load_technical_indicators.py - see steering/DATA_LOADERS.md), not
        orchestrator outputs, and Phase 7 (signal_generation) has a dedicated
        fail-closed halt when buy_sell_daily is stale (see phase7_signal_generation.py).
        A prior version of this check excluded them as "orchestrator outputs written by
        Phase 5/6" - that premise was wrong (no orchestrator phase writes either table)
        and caused this health panel to report HEALTHY while Phase 7 was actively
        halting on the same staleness.

        stock_scores is excluded - Phase 1 already runs its own dedicated completeness/
        freshness check for it (see phase1_data_freshness.py), so double-counting it
        here would just duplicate that alert under a coarser (day-granularity) check.

        economic_data is excluded - it stores FRED macro series with no pipeline loader;
        algo_market_exposure.py handles missing rows with safe defaults.
        """
        critical_tables = {
            "stock_symbols",
            "price_daily",
            "market_health_daily",
            "buy_sell_daily",
            "technical_data_daily",
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
    # sla_days reflects the REAL once-per-trading-day cadence documented in
    # steering/DATA_LOADERS.md (price_daily/technical_data_daily/buy_sell_daily/
    # market_health_daily are all EOD-pipeline outputs expected fresh as of the last
    # completed trading day). A prior version padded these to sla_days=5 as a blunt
    # workaround for not knowing about weekend/holiday gaps - that hid genuine 2-4
    # day staleness (a real loader failure) behind the same threshold meant to
    # tolerate a long weekend. _gap_adjusted_sla() now adds back exactly the size of
    # any actual weekend/holiday gap via MarketCalendar, so a real gap is tolerated
    # without also tolerating a same-length loader outage on a normal week.
    CRITICAL_TABLES: dict[str, dict[str, str | int]] = {
        "stock_symbols": {"date_column": "created_at", "sla_days": 30},
        "price_daily": {"date_column": "date", "sla_days": 1},
        "buy_sell_daily": {"date_column": "date", "sla_days": 1},
        "technical_data_daily": {"date_column": "date", "sla_days": 1},
        "stock_scores": {"date_column": "updated_at", "sla_days": 5},
        "economic_data": {"date_column": "date", "sla_days": 7},
        "market_health_daily": {"date_column": "date", "sla_days": 1},
        "analyst_sentiment_analysis": {"date_column": "updated_at", "sla_days": 7},
        "earnings_calendar": {"date_column": "created_at", "sla_days": 30},
    }

    # Tables that only update once per trading day - a weekend/holiday gap since the
    # last completed trading day is expected staleness, not an incident. Tables not in
    # this set (e.g. stock_symbols, earnings_calendar with sla_days=30) already have
    # enough slack that a multi-day gap is a rounding error and don't need adjustment.
    TRADING_DAY_CADENCE_TABLES = frozenset(
        {"price_daily", "buy_sell_daily", "technical_data_daily", "market_health_daily"}
    )

    @staticmethod
    def _trading_day_gap_days(today: _date) -> int:
        """Calendar days between today and the most recent completed trading day before it.

        1 on a normal day (yesterday traded); >1 across a weekend/holiday (e.g. 3 on a
        Monday following a Friday close). Mirrors the logic already proven correct in
        scripts/monitor_data_staleness.py rather than re-deriving a second version.
        """
        from datetime import timedelta

        prev_trading_day = today - timedelta(days=1)
        for _ in range(10):
            if MarketCalendar.is_trading_day(prev_trading_day):
                break
            prev_trading_day -= timedelta(days=1)
        return (today - prev_trading_day).days

    def _gap_adjusted_sla(self, table_name: str, base_sla_days: int, today: _date) -> int:
        """Pad base_sla_days by any weekend/holiday gap for trading-day-cadence tables."""
        if table_name not in self.TRADING_DAY_CADENCE_TABLES:
            return base_sla_days
        gap_days = self._trading_day_gap_days(today)
        return base_sla_days + max(0, gap_days - 1)

    def check_table_health(self, cur: Any, table_name: str, date_column: str | None, sla_days: int) -> TableHealth:
        effective_sla_days = self._gap_adjusted_sla(table_name, sla_days, datetime.now(EASTERN_TZ).date())
        health = TableHealth(table_name=table_name, status=HealthStatus.ERROR, sla_days=effective_sla_days)

        try:
            safe_table = assert_safe_table(table_name)

            # Use pg_class.reltuples for O(1) approximate row count instead of
            # COUNT(*) full scan on large tables. reltuples is only refreshed by
            # ANALYZE/VACUUM though, and Postgres's autovacuum-analyze threshold
            # (~10% of rows changed, floor 50 rows) means a table that only ever
            # gains 1-2 rows/day - e.g. market_exposure_daily, algo_risk_daily -
            # can sit at reltuples=0 indefinitely even with real data present,
            # permanently misreporting MISSING/empty. COUNT(*) is trivially cheap
            # below a few hundred thousand rows, so fall back to an exact count
            # whenever the estimate is small instead of trusting a stale stat.
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
                estimated_cnt: int = int(greatest_val) if greatest_val is not None else int(result.get("cnt") or 0)
            else:
                estimated_cnt = int(result[0])

            EXACT_COUNT_THRESHOLD = 100_000
            if estimated_cnt < EXACT_COUNT_THRESHOLD:
                cur.execute(f"SELECT COUNT(*) FROM {safe_table}")
                exact_result = cur.fetchone()
                exact_cnt = (
                    int(exact_result.get("count", 0))
                    if isinstance(exact_result, dict)
                    else int(exact_result[0])
                    if exact_result
                    else 0
                )
                health.row_count = exact_cnt
            else:
                health.row_count = estimated_cnt

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

            # Determine status based on the gap-adjusted SLA (see _gap_adjusted_sla)
            if health.age_days > (effective_sla_days * 2):
                health.status = HealthStatus.VERY_STALE
            elif health.age_days > effective_sla_days:
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
        """Log pipeline health to database for historical tracking.

        Session 299 FIX: Preserve original loader error_message instead of overwriting.
        When a loader fails, its error message should be kept, not replaced with
        a generic "no data found" message from the health check.
        """
        try:
            with DatabaseContext("write") as cur:
                if status.tables:
                    # Session 299 FIX: Fetch existing error_message for each table
                    # Only overwrite if health check found a NEW problem
                    cur.execute("""
                        SELECT table_name, error_message FROM data_loader_status
                        WHERE table_name = ANY(%s)
                    """, (list(status.tables.keys()),))
                    existing_errors = {row[0]: row[1] for row in cur.fetchall()}

                    insert_values = [
                        (
                            table_health.table_name,
                            table_health.status.value,
                            table_health.row_count,
                            table_health.latest_date,
                            table_health.age_days,
                            # If this check found ERROR, use its (fresh) error_message.
                            # If the table is now HEALTHY, clear it - an old error sitting
                            # next to a fresh last_updated timestamp reads as "still broken"
                            # on the health panel even after the table has recovered.
                            # Otherwise (STALE/VERY_STALE/MISSING but not erroring), preserve
                            # whatever context was already recorded.
                            table_health.error_message
                                if table_health.status == HealthStatus.ERROR
                                else (None if table_health.status == HealthStatus.HEALTHY
                                      else existing_errors.get(table_health.table_name)),
                            # Was previously never written by any code path (a static value
                            # from a one-time seed insert, unrelated to the sla_days actually
                            # used to compute `status` above) - wire it to the real,
                            # gap-adjusted threshold so this column stops silently
                            # contradicting the status it sits next to.
                            table_health.sla_days,
                        )
                        for table_health in status.tables.values()
                    ]
                    cur.executemany(
                        """
                        INSERT INTO data_loader_status
                        (table_name, status, row_count, latest_date, age_days, error_message, stale_threshold_days, last_updated)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                        ON CONFLICT (table_name)
                        DO UPDATE SET
                            status = EXCLUDED.status,
                            row_count = EXCLUDED.row_count,
                            latest_date = EXCLUDED.latest_date,
                            age_days = EXCLUDED.age_days,
                            error_message = EXCLUDED.error_message,
                            stale_threshold_days = EXCLUDED.stale_threshold_days,
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
