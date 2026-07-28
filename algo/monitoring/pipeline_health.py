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
    DEPRECATED = "DEPRECATED"  # Table intentionally frozen - see KNOWN_DEPRECATED_TABLES


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
        # DEPRECATED counts toward "no action needed", same as HEALTHY: these tables are
        # expected to sit frozen (loader deliberately retired, see KNOWN_DEPRECATED_TABLES),
        # so counting them against coverage_pct/healthy_count would make 100% pipeline
        # coverage permanently unreachable for a reason that isn't a real degradation.
        return self.status in (HealthStatus.HEALTHY, HealthStatus.DEPRECATED)

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
        "earnings_calendar": {"date_column": "created_at", "sla_days": 30},
    }

    # Tables that only update once per trading day - a weekend/holiday gap since the
    # last completed trading day is expected staleness, not an incident. Tables not in
    # this set (e.g. stock_symbols, earnings_calendar with sla_days=30) already have
    # enough slack that a multi-day gap is a rounding error and don't need adjustment.
    TRADING_DAY_CADENCE_TABLES = frozenset(
        {"price_daily", "buy_sell_daily", "technical_data_daily", "market_health_daily"}
    )

    # Tables whose loaders were deliberately removed/consolidated (see
    # loaders/DEPRECATED_LOADERS.md) - they are expected to sit frozen at whatever date
    # they last held, not creeping staleness needing investigation. Confirmed live
    # 2026-07-20: these were showing STALE/VERY_STALE/MISSING on every health sweep
    # indistinguishable from genuine loader breakage (e.g. get_loader_health()'s
    # stale_loaders list), which is exactly the kind of noise that made a REAL bug
    # (sector_performance silently stuck since 2026-07-10, fixed same session) hard to
    # spot in a wall of expected-but-unlabeled staleness. Does not include sector_performance/
    # sector_ranking/market_sentiment/market_exposure_daily - those are still actively
    # written by their (consolidated) loaders and must keep alerting if they go stale.
    KNOWN_DEPRECATED_TABLES = frozenset(
        {
            "price_extremes_52week",  # ORPHANED per DEPRECATED_LOADERS.md - load_price_extremes.py removed
            "market_cap_computed",  # ORPHANED per DEPRECATED_LOADERS.md - load_market_cap_computed.py removed
            "yfinance_snapshot",  # DEPRECATED per DEPRECATED_LOADERS.md - frozen at Session 275
            "fear_greed_index",  # Standalone legacy table; superseded by market_sentiment.fear_greed_index column
            # Confirmed live 2026-07-20 via full-repo search: zero INSERT/UPDATE writer exists
            # for any of the following, in loaders/ or anywhere else - only read call sites
            # (API routes, sql_safety allowlist, schema_definitions). They are not "stale",
            # they are frozen at whatever data they held when their (never-built, or removed)
            # loader last ran, indistinguishable on the health panel from a genuine same-day
            # loader failure without this exclusion - same noise class as the four tables above.
            "ttm_income_statement",  # loaders/load_financial_statements.py: "ttm" period combos
            "ttm_cash_flow",  # explicitly removed 2026-07-13 (SecEdgarStatementLoader never
            # supported period='ttm'; both combos crashed on init every run) - see
            # get_all_statement_configs() docstring in that file.
            "buy_sell_weekly",  # No loader ever existed for weekly/monthly buy_sell aggregates -
            "buy_sell_monthly",  # load_buy_sell_daily.py is the only buy_sell_* loader, and it
            "buy_sell_daily_etf",  # deliberately excludes ETFs (exclude_etfs_from_symbols=True,
            "buy_sell_weekly_etf",  # "Trading signals for stocks only, not ETFs").
            "buy_sell_monthly_etf",
            "seasonality_monthly_stats",  # No writer found anywhere in the codebase.
            # analyst_upgrade_downgrade REMOVED from this exclusion 2026-07-27: restored a real
            # writer (load_analyst_upgrade_downgrade.py, yfinance-sourced) wired into
            # eod_pipeline's AaiiSentiment -> AnalystUpgradeDowngrade -> MarketStatusDaily chain
            # and scripts/local_loader_scheduler.py - staleness should now be monitored like any
            # other real loader, not silently excluded.
            # analyst_sentiment_analysis REMOVED from this exclusion 2026-07-27: same restoration,
            # separate table - real writer (load_analyst_sentiment_analysis.py, yfinance-sourced)
            # wired into eod_pipeline's AnalystUpgradeDowngrade -> AnalystSentimentAnalysis ->
            # MarketStatusDaily chain and scripts/local_loader_scheduler.py.
            "portfolio_holdings",  # No writer found anywhere in the codebase.
            "algo_trades_archive",  # No writer found anywhere in the codebase.
            # Confirmed live 2026-07-27: both 0 rows, no INSERT/UPDATE writer anywhere in
            # loaders/ - real 8-K/dividend data is written to current_reports_8k and
            # dividend_data respectively (see utils/db/sql_safety.py SAFE_TABLES). These two
            # names are leftover data_loader_status rows from an earlier design iteration.
            "sec_dividends",  # Superseded by dividend_data
            "sec_material_events",  # Superseded by current_reports_8k
            # sec_cash_flow_metrics REMOVED from scheduling 2026-07-27 (loaders/DEPRECATED_LOADERS.md):
            # its 3 fields exactly duplicate quality_metrics formulas already computed by
            # load_value_quality_growth_metrics.py, zero incremental signal for the real SEC API
            # cost. Frozen at 5508 rows from its last run - added here proactively so it reports
            # DEPRECATED once that data ages past the 7-day default secondary-table SLA, instead
            # of a false STALE/CRITICAL alarm for a table nothing writes anymore.
            "sec_cash_flow_metrics",
            # Confirmed live 2026-07-27: 0 rows, no INSERT/UPDATE writer anywhere in the
            # codebase - already documented as such in scripts/audit_system_health.py
            # ("never populated") and scripts/monitor_data_staleness.py, but never added
            # here, so every pipeline health sweep still reported it MISSING (counting
            # against coverage_pct/healthy_count) instead of DEPRECATED like its
            # already-covered siblings. Real portfolio performance now comes from
            # algo_performance_daily/algo_risk_daily (see commit 47ff447db).
            "equity_curve_daily",
        }
    )

    # Tables with a real, active loader whose intended cadence is longer than the 7-day
    # default applied to every table outside CRITICAL_TABLES (see the "second sweep" in
    # get_pipeline_status()). Without this, a monthly-refresh table would show
    # STALE/VERY_STALE every single day of its normal life, indistinguishable from an
    # actually-broken daily table - the same false-positive-noise problem
    # KNOWN_DEPRECATED_TABLES solves for tables with no writer at all, but for tables that
    # ARE being written, just less often than daily.
    SECONDARY_TABLE_SLA_OVERRIDES: dict[str, int] = {
        # loaders/load_prices.py resamples these from price_daily/etf_price_daily via
        # derive_aggregate_prices() (targets = (("price_weekly", "week", 28),
        # ("price_monthly", "month", 92)) and the etf_ equivalents). The stock-side
        # price_monthly entry was missing here (only its etf_ counterpart was listed) -
        # confirmed live 2026-07-27: price_monthly's own row (age 26 days, same as
        # etf_price_monthly's) fell through to the 7-day default and reported VERY_STALE
        # while etf_price_monthly reported HEALTHY for the identical situation, even
        # though AAPL's price_monthly row was verified up to date (high/low/close exactly
        # matching price_daily's July aggregate) - the row's `date` column is a bucket key
        # (pinned to the 1st of the month) that legitimately stays constant while
        # open/high/low/close/volume are refreshed daily, so a monthly table needs a
        # month-scale SLA regardless of asset class.
        "price_monthly": 35,
        "etf_price_monthly": 35,
    }

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
                if greatest_val is None:
                    # CRITICAL: If GREATEST() returns NULL, the table is empty (all values are NULL)
                    # Do NOT default to result.get("cnt") or 0 - that silently hides query failures
                    # or missing column issues. Null = empty, not "unknown".
                    estimated_cnt = 0
                else:
                    estimated_cnt = int(greatest_val)
            else:
                estimated_cnt = int(result[0])

            exact_count_threshold = 100_000
            if estimated_cnt < exact_count_threshold:
                cur.execute(f"SELECT COUNT(*) FROM {safe_table}")
                exact_result = cur.fetchone()
                # CRITICAL: Count query must return exactly one row with COUNT(*) result.
                # If it doesn't, the query failed - don't silently default to 0.
                if exact_result is None:
                    raise RuntimeError(f"COUNT(*) query for {table_name} returned None - query execution failed")
                if isinstance(exact_result, dict):
                    exact_cnt = exact_result.get("count")
                    if exact_cnt is None:
                        raise RuntimeError(
                            f"COUNT(*) query for {table_name} returned dict without 'count' key. "
                            f"Keys: {list(exact_result.keys())}. "
                            f"This indicates a query result mismatch - expected DictCursor with 'count' key."
                        )
                    exact_cnt = int(exact_cnt)
                else:
                    if len(exact_result) < 1 or exact_result[0] is None:
                        raise RuntimeError(
                            f"COUNT(*) query for {table_name} returned empty or NULL result: {exact_result}"
                        )
                    exact_cnt = int(exact_result[0])
                health.row_count = exact_cnt
            else:
                health.row_count = estimated_cnt

            if health.row_count == 0:
                # A deprecated table (deliberately retired loader, see KNOWN_DEPRECATED_TABLES)
                # that never got a single row written is still expected to sit frozen, not an
                # incident - without this check it would report MISSING and count against
                # coverage_pct/healthy_count forever, the exact false-alarm noise
                # KNOWN_DEPRECATED_TABLES exists to prevent (see is_healthy above).
                if table_name in self.KNOWN_DEPRECATED_TABLES:
                    health.status = HealthStatus.DEPRECATED
                    health.error_message = "Table intentionally frozen (deprecated loader) - see KNOWN_DEPRECATED_TABLES"
                else:
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
                latest_date = result.get(safe_date_col)
                if latest_date is None:
                    latest_date = result.get("date")
                    if latest_date is not None:
                        logger.debug(
                            f"[PIPELINE_HEALTH] {safe_table}: Using fallback 'date' column "
                            f"(expected '{safe_date_col}'). Result keys: {list(result.keys())}"
                        )
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

            # Determine status based on the gap-adjusted SLA (see _gap_adjusted_sla) - unless
            # this table's loader was deliberately retired (KNOWN_DEPRECATED_TABLES), in which
            # case it's expected to sit frozen and age_days climbing is not an incident.
            if table_name in self.KNOWN_DEPRECATED_TABLES:
                health.status = HealthStatus.DEPRECATED
            elif health.age_days > (effective_sla_days * 2):
                health.status = HealthStatus.VERY_STALE
            elif health.age_days > effective_sla_days:
                health.status = HealthStatus.STALE
            else:
                health.status = HealthStatus.HEALTHY

        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            health.status = HealthStatus.ERROR
            health.error_message = str(e)

        return health

    def get_pipeline_status(self) -> PipelineStatus:
        status = PipelineStatus()

        try:
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
                    default_sla_days = 7

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
                                self.SECONDARY_TABLE_SLA_OVERRIDES.get(table_name, default_sla_days),
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

                # Third: detect loaders orphaned mid-run (see _check_stuck_loaders docstring).
                try:
                    for stuck in self._check_stuck_loaders(cur):
                        table_name = stuck["table_name"]
                        msg = (
                            f"{table_name}: loader stuck in RUNNING status, no heartbeat "
                            f"update in {stuck['stale_minutes'] / 60:.1f}h "
                            f"(started {stuck['execution_started']}) "
                            f"- likely crashed or was killed without updating status"
                        )
                        existing = status.tables.get(table_name)
                        if existing is not None:
                            existing.status = HealthStatus.ERROR
                            existing.error_message = msg
                            health = existing
                        else:
                            health = TableHealth(table_name=table_name, status=HealthStatus.ERROR, error_message=msg)
                            status.tables[table_name] = health

                        if health.is_critical:
                            status.critical_alerts.append(f"CRITICAL: {msg}")
                        else:
                            status.warnings.append(f"WARNING: {msg}")
                except Exception as e:
                    logger.error(f"Error checking for orphaned RUNNING loaders: {e}")
                    # Continue anyway - this check is additive, not required for the rest

        except (ValueError, ZeroDivisionError, TypeError) as e:
            logger.error(f"Cannot check pipeline status: {e}")
            status.is_healthy = False
            status.critical_alerts.append(f"Database connection failed: {e}")
            return status

        # Overall health determination
        has_critical_issues = any(not t.is_healthy and t.is_critical for t in status.tables.values())
        status.is_healthy = not has_critical_issues and len(status.critical_alerts) == 0

        return status

    def _check_stuck_loaders(self, cur: Any) -> list[dict[str, Any]]:
        """Find loaders orphaned mid-run: status=RUNNING with a frozen heartbeat.

        update_loader_status("RUNNING") is written at loader start, and a background
        heartbeat thread (60s interval, see utils/loader_infrastructure.py
        start_heartbeat) refreshes last_updated for as long as the process stays
        alive - both the normal success path (_update_final_status) and the
        exception handler rewrite status away from RUNNING before exit. Neither runs
        on a hard kill (OOM, or ecs.stop_task() from lambda/loader-timeout-guardian,
        which only calls ECS StopTask and never touches this table) - SIGTERM/SIGKILL
        bypasses Python's except block entirely, so the row is left at status=RUNNING
        with a frozen last_updated forever. Every other check in this file derives
        health from the target table's own row age, which still looks fresh from
        whatever the last *successful* run loaded - masking the fact that the most
        recent attempt crashed. 15 minutes is 15x the heartbeat interval, comfortably
        beyond any live GC/DB-hiccup pause.
        """
        cur.execute(
            """
            SELECT table_name, execution_started, last_updated,
                   EXTRACT(EPOCH FROM (NOW() - last_updated)) / 60 AS stale_minutes
            FROM data_loader_status
            WHERE status = 'RUNNING'
              AND last_updated < NOW() - INTERVAL '15 minutes'
            """
        )
        results = []
        for row in cur.fetchall():
            if isinstance(row, dict):
                table_name = row["table_name"]
                execution_started = row["execution_started"]
                stale_minutes = float(row["stale_minutes"])
            else:
                table_name, execution_started, _last_updated, stale_minutes = row
                stale_minutes = float(stale_minutes)
            results.append(
                {
                    "table_name": table_name,
                    "execution_started": execution_started,
                    "stale_minutes": stale_minutes,
                }
            )
        return results

    def _infer_date_column(self, cur: Any, table_name: str) -> str | None:
        """Infer the date column for a table by checking column existence AND content.

        Tries in order: date, updated_at, last_updated_at, created_at, date_added. A column
        that exists but is NULL for every row (e.g. value_metrics.date, analyst_upgrade_downgrade.date -
        dead/unused columns left over from an old schema, with the real timestamp actually
        in updated_at/action_date) used to be picked anyway since only existence was checked,
        making check_table_health()'s "SELECT col ORDER BY col DESC LIMIT 1" return NULL and
        report a table with fresh, real data as HealthStatus.MISSING. Requiring at least one
        non-null value before accepting a candidate column fixes that false positive and falls
        through to the next candidate instead.

        last_updated_at added 2026-07-21: algo_runtime_state (the RDS-fallback halt-flag state
        table, actively upserted on every orchestrator run) was falling through to created_at,
        which PostgreSQL sets once at row creation and never touches again on UPDATE - so a
        single-row state table updated seconds ago read as VERY_STALE (32 days) forever after
        its first insert. Confirmed live: last_updated_at=today, created_at=2026-06-19.
        Tried before created_at since, like updated_at, it tracks real per-row freshness rather
        than row-creation time.
        Returns None if no populated date-like column is found.
        """
        try:
            safe_table = assert_safe_table(table_name)
            for col in ["date", "updated_at", "last_updated_at", "created_at", "date_added"]:
                safe_col = assert_safe_column(col)
                cur.execute(
                    "SELECT 1 FROM information_schema.columns WHERE table_name = %s AND column_name = %s LIMIT 1",
                    (table_name, col),
                )
                if not cur.fetchone():
                    continue
                cur.execute(f"SELECT 1 FROM {safe_table} WHERE {safe_col} IS NOT NULL LIMIT 1")
                if cur.fetchone():
                    return col
                logger.debug(f"{table_name}.{col} exists but is NULL for every row - trying next candidate")
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
                    # Also fetch consecutive_failures: this age-based freshness sweep runs
                    # unconditionally on every orchestrator run (pre-Phase-1) and previously
                    # overwrote `status` unconditionally too - silently erasing a loader's real
                    # FAILED/TIMEOUT status (set by LoaderStatusManager.mark_failed(), tracked
                    # via consecutive_failures) the moment this check ran again, as long as the
                    # target table's existing data still looked fresh enough by age. A loader
                    # that genuinely fails (auth error, rate limit, crash) would show FAILED for
                    # under a minute before the next orchestrator run's health sweep silently
                    # relabeled it HEALTHY - confirmed live 2026-07-27: data_loader_status rows
                    # with consecutive_failures > 0 sat next to status='HEALTHY'/'STALE', not the
                    # FAILED/TIMEOUT LoaderStatusManager actually recorded.
                    cur.execute(
                        """
                        SELECT table_name, error_message, status, consecutive_failures
                        FROM data_loader_status
                        WHERE table_name = ANY(%s)
                    """,
                        (list(status.tables.keys()),),
                    )
                    existing_db_rows = cur.fetchall()
                    existing_errors = {row[0]: row[1] for row in existing_db_rows}
                    existing_failures = {row[0]: (row[1], row[2]) for row in existing_db_rows if (row[3] or 0) > 0}

                    insert_values = []
                    for table_health in status.tables.values():
                        # Preserve a real, unresolved loader failure (LoaderStatusManager's
                        # FAILED/TIMEOUT, tracked via consecutive_failures) instead of letting
                        # this age-based freshness sweep silently overwrite it - unless this
                        # sweep found something worth surfacing on its own (MISSING/ERROR are
                        # at least as severe as an unresolved FAILED/TIMEOUT and reflect this
                        # check's own live query, not a stale count). Applies to both status
                        # and error_message together so the two never end up telling different
                        # stories (e.g. status=FAILED next to a HEALTHY-cleared error_message).
                        preserved = existing_failures.get(table_health.table_name)

                        if preserved is not None and table_health.status not in (
                            HealthStatus.MISSING,
                            HealthStatus.ERROR,
                        ):
                            status_value = preserved[1]
                            error_value = preserved[0]
                        else:
                            status_value = table_health.status.value
                            # If the table is now HEALTHY, clear the error - an old error sitting
                            # next to a fresh last_updated timestamp reads as "still broken" on
                            # the health panel even after the table has recovered.
                            # Otherwise, use this check's own fresh error_message whenever it set
                            # one (ERROR always does; DEPRECATED/MISSING do for several of their
                            # branches - e.g. check_table_health's "Table intentionally frozen"
                            # and "Table is empty" messages). Only fall back to the previously
                            # recorded message for branches that don't compute their own
                            # (STALE/VERY_STALE, and DEPRECATED-with-data) - previously ANY
                            # non-ERROR/non-HEALTHY status preserved the old message unconditionally,
                            # so a table whose status changed from a real problem (e.g. "Unknown
                            # table X (not in whitelist)") to DEPRECATED/MISSING with its own fresh,
                            # correct explanation kept showing the stale wrong-cause message forever
                            # - confirmed live 2026-07-27: sec_dividends/sec_material_events/
                            # analyst_sentiment_analysis still showed "not in whitelist" hours after
                            # that whitelist gap was fixed (commit 349ccef9b), because check_table_health
                            # now correctly computes "Table intentionally frozen ... KNOWN_DEPRECATED_TABLES"
                            # for them but this write path never let that fresh message through.
                            if table_health.status == HealthStatus.HEALTHY:
                                error_value = None
                            elif table_health.error_message is not None:
                                error_value = table_health.error_message
                            else:
                                error_value = existing_errors.get(table_health.table_name)

                        insert_values.append(
                            (
                                table_health.table_name,
                                status_value,
                                table_health.row_count,
                                table_health.latest_date,
                                table_health.age_days,
                                error_value,
                                # Was previously never written by any code path (a static value
                                # from a one-time seed insert, unrelated to the sla_days actually
                                # used to compute `status` above) - wire it to the real,
                                # gap-adjusted threshold so this column stops silently
                                # contradicting the status it sits next to.
                                table_health.sla_days,
                                # last_updated must reflect real data recency (latest_date, the
                                # table's own most recent row), not "when this health check ran".
                                # This bulk executemany runs in ONE transaction on every orchestrator
                                # run (pre-Phase-1, unconditional) - Postgres's NOW() is fixed for the
                                # whole transaction, so the old `last_updated = NOW()` stamped every
                                # one of the ~95 tracked tables with the SAME timestamp every run,
                                # for EVERY table including ones with their own precise per-loader
                                # last_updated (load_prices.py etc. already set this correctly via a
                                # table-name-scoped UPDATE) - clobbering it. Confirmed live: every row
                                # in data_loader_status shared one identical microsecond-precision
                                # timestamp, and /api/algo/data-status (which computes age_hours/stale
                                # status directly off this column, per its own last_updated.date() vs
                                # expected_date comparison) reported every table as equally ~fresh
                                # regardless of true staleness - masking exactly the kind of stale-data
                                # condition this health check exists to surface. Fall back to NOW()
                                # only when no latest_date could be determined (no usable date column
                                # on that table) - see _infer_date_column's "skipping age check" path.
                                table_health.latest_date,
                            )
                        )
                    cur.executemany(
                        """
                        INSERT INTO data_loader_status
                        (table_name, status, row_count, latest_date, age_days, error_message, stale_threshold_days, last_updated)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, COALESCE(%s::timestamptz, NOW()))
                        ON CONFLICT (table_name)
                        DO UPDATE SET
                            status = EXCLUDED.status,
                            row_count = EXCLUDED.row_count,
                            latest_date = EXCLUDED.latest_date,
                            age_days = EXCLUDED.age_days,
                            error_message = EXCLUDED.error_message,
                            stale_threshold_days = EXCLUDED.stale_threshold_days,
                            last_updated = EXCLUDED.last_updated
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
