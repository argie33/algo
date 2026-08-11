#!/usr/bin/env python3
"""Specialized data checks - earnings, fundamentals, derivatives, sentiment."""

import logging
from datetime import date as _date
from datetime import datetime, timezone
from typing import Any

import psycopg2

from algo.infrastructure.config.sql_intervals import get_interval_sql
from utils.db import assert_safe_column, assert_safe_table

from ..base import BaseCheck, CheckResult
from ..config import ERROR, INFO, WARN

logger = logging.getLogger(__name__)


class SpecializedChecker(BaseCheck):
    def run(self, cur: Any) -> list[CheckResult]:
        """Execute specialized checks."""
        self.results = []

        checks = [
            ("earnings_data", self.check_earnings_data),
            ("fundamental_data", self.check_fundamental_data),
            ("derived_metrics", self.check_derived_metrics),
            ("sentiment_aggregate", self.check_sentiment_aggregate),
            ("trade_recorder_columns", self.check_trade_recorder_columns),
        ]
        for fn_name, fn in checks:
            sp = f"sp_spec_{fn_name}"
            try:
                cur.execute(f"SAVEPOINT {sp}")
            except psycopg2.DatabaseError as e:
                logger.critical(f"Database error creating SAVEPOINT {sp}: {e} - data patrol cannot proceed safely")
                self.log(
                    fn_name,
                    ERROR,
                    fn_name,
                    "SAVEPOINT creation failed - database state unknown",
                    None,
                )
                continue
            try:
                fn(cur)
            except Exception as e:
                logger.critical(f"Specialized {fn_name} check FAILED: {e} - results are incomplete")
                self.log(
                    fn_name,
                    ERROR,
                    fn_name,
                    "Check execution failed - treating as critical failure",
                    {"error": str(e)},
                )
            finally:
                try:
                    cur.execute(f"ROLLBACK TO SAVEPOINT {sp}")
                except psycopg2.DatabaseError as e:
                    logger.warning(f"Failed to rollback SAVEPOINT {sp}: {e} - transaction state may be inconsistent")

        return self.results

    def check_earnings_data(self, cur: Any) -> None:
        today = _date.today()
        # BUG FOUND 2026-08-11 (independently found+fixed by two concurrent sessions, merged
        # here): "earnings_estimates" and "earnings_estimate_revisions" were never real table
        # names - confirmed against information_schema.tables. The actual forward-EPS table
        # (real writer: load_analyst_earnings_estimates.py, 38k+ rows) is
        # "analyst_earnings_estimates"; no "revisions" table has ever existed anywhere in this
        # codebase (no loader, no migration - revision data is computed inline from
        # analyst_earnings_estimates by load_enhanced_quality_growth_metrics.py, never
        # persisted to its own table).
        #
        # "earnings_history" does exist but is a permanently-empty legacy table (0 rows, no
        # writer anywhere - see loaders/loader_registry.py's own comment calling it out as
        # legacy/dead) and is already monitored at INFO severity in staleness.py, so dropping
        # the WARN-severity duplicate here doesn't lose coverage. In its place: the real,
        # actively-updated table this data actually lives in - earnings_calendar_sec (353k+
        # rows, updated daily per loader_registry.py's comment) - which nothing else in
        # data_patrol was monitoring at all. Live-verified via `python -m algo.algo_data_patrol
        # --quick --json`: patrol readiness went from ready=False (guaranteed earnings_estimates
        # ERROR every run) to ready=True with real data (analyst_earnings_estimates: 38,617
        # rows/99.8% coverage; earnings_calendar_sec: fresh same-day).
        sources = [
            ("analyst_earnings_estimates", ["created_at"], 7, WARN),
            ("earnings_calendar_sec", ["created_at"], 3, WARN),
        ]

        for tbl, col_options, max_days, sev in sources:
            sp = f"sp_earnings_staleness_{tbl}"
            cur.execute(f"SAVEPOINT {sp}")
            try:
                col = col_options[0]
                tbl_safe = assert_safe_table(tbl)
                cur.execute(f"""
                    SELECT COUNT(*) as count, MAX({col}::date) as latest
                    FROM {tbl_safe}
                """)
                result = cur.fetchone()
                if result is None:
                    raise ValueError(f"Query returned no results for {tbl}")
                count = result.get("count") if hasattr(result, "get") else result[0]
                latest = result.get("latest") if hasattr(result, "get") else result[1]

                if not latest:
                    self.log(
                        "earnings_staleness",
                        WARN,
                        tbl,
                        f"{tbl} is empty",
                        {"count": 0},
                    )
                else:
                    if isinstance(latest, str):
                        latest = _date.fromisoformat(latest)
                    age = (today - latest).days
                    if age > max_days:
                        self.log(
                            "earnings_staleness",
                            sev,
                            tbl,
                            f"{tbl} stale: {age}d > {max_days}d",
                            {"latest": str(latest), "age_days": age},
                        )
                    else:
                        self.log(
                            "earnings_staleness",
                            INFO,
                            tbl,
                            f"{tbl} fresh ({age}d old)",
                            {"latest": str(latest), "count": count},
                        )
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                # BUG FOUND 2026-08-11: without a per-source SAVEPOINT, a failure on one
                # table (e.g. relation does not exist) aborted the whole transaction, so
                # every subsequent source in this loop failed with the misleading
                # "current transaction is aborted" instead of its own real error - and the
                # coverage check below inherited the same aborted state. Roll back to this
                # source's own savepoint so later sources/checks run against a clean
                # transaction regardless of what this one hit.
                cur.execute(f"ROLLBACK TO SAVEPOINT {sp}")
                logger.critical(f"Earnings data check for {tbl} FAILED: {e} - assuming critical data missing")
                self.log(
                    "earnings_staleness",
                    ERROR,
                    tbl,
                    f"Check FAILED (table access error): {e}",
                    None,
                )
            else:
                cur.execute(f"RELEASE SAVEPOINT {sp}")

        # Check earnings coverage
        sp_cov = "sp_earnings_coverage"
        cur.execute(f"SAVEPOINT {sp_cov}")
        try:
            interval_7d = get_interval_sql("7d")
            cur.execute(f"""
                SELECT
                    COUNT(DISTINCT e.symbol) AS est_syms,
                    COUNT(DISTINCT p.symbol) AS price_syms
                FROM price_daily p
                LEFT JOIN analyst_earnings_estimates e
                    ON e.symbol = p.symbol
                   AND e.created_at >= CURRENT_DATE - {interval_7d}
                WHERE p.date >= CURRENT_DATE - {interval_7d}
            """)
            row = cur.fetchone()
            if row is None:
                raise ValueError("Earnings coverage query returned no results - database state corrupted")
            est_syms = row.get("est_syms") if hasattr(row, "get") else row[0]
            price_syms = row.get("price_syms") if hasattr(row, "get") else row[1]
            if est_syms is None:
                raise ValueError("COUNT(DISTINCT e.symbol) returned NULL - earnings estimates query may have failed")
            if price_syms is None:
                raise ValueError("price_daily COUNT(DISTINCT symbol) returned NULL - loader may be stalled")
            est_syms = int(est_syms)
            price_syms = int(price_syms)
            pct = est_syms / price_syms * 100
            sev = WARN if pct < 80 else INFO
            self.log(
                "earnings_coverage",
                sev,
                "analyst_earnings_estimates",
                f"{pct:.1f}% symbol coverage ({est_syms}/{price_syms})",
                {"coverage_pct": round(pct, 1)},
            )
        except (
            psycopg2.DatabaseError,
            psycopg2.OperationalError,
            ValueError,
            ZeroDivisionError,
            TypeError,
        ) as e:
            cur.execute(f"ROLLBACK TO SAVEPOINT {sp_cov}")
            logger.critical(f"Earnings coverage check FAILED: {e} - cannot validate data completeness")
            self.log(
                "earnings_coverage",
                ERROR,
                "analyst_earnings_estimates",
                f"Check FAILED: {e}",
                None,
            )
        else:
            cur.execute(f"RELEASE SAVEPOINT {sp_cov}")

    def check_fundamental_data(self, cur: Any) -> None:
        today = _date.today()
        table_checks = [
            # DISABLED 2026-08-06: SEC financial statement loaders hang for 5+ hours and get force-killed.
            # Removed from monitoring since they're no longer actively loaded.
            # ("quarterly_income_statement", "created_at", 45, WARN),
            # ("quarterly_balance_sheet", "created_at", 45, WARN),
            # ("quarterly_cash_flow", "created_at", 45, WARN),
            # ("annual_income_statement", "created_at", 120, WARN),
            # ("annual_balance_sheet", "created_at", 120, WARN),
            # ("annual_cash_flow", "created_at", 120, WARN),
            # BUG FOUND 2026-08-11: key_metrics has had no active writer since 2026-05-21
            # (confirmed: not in loaders/loader_registry.py, not scheduled anywhere) - this
            # check was correctly flagging it as stale every day, but that masked the real
            # gap: its one live consumer (lambda/api/routes/market.py's cap-distribution
            # endpoint) was silently serving ~3-month-stale data the whole time. Migrated the
            # API route to sec_valuations (actively written daily by the scheduled
            # load_sec_valuations.py loader) - monitor that table instead, since it's the one
            # actually feeding production now.
            ("sec_valuations", "created_at", 3, WARN),
        ]

        try:
            for tbl, col, _max_days, _sev in table_checks:
                assert_safe_table(tbl)
                assert_safe_column(col)

            union_parts = []
            for tbl, col, _max_days, _sev in table_checks:
                tbl_safe = assert_safe_table(tbl)
                col_safe = assert_safe_column(col)
                union_parts.append(
                    f"SELECT '{tbl}' as tbl_name, MAX({col_safe}::date) as latest, COUNT(*) as total, COUNT(DISTINCT symbol) as unique_syms FROM {tbl_safe}"
                )

            union_query = " UNION ALL ".join(union_parts)
            cur.execute(union_query)

            results_by_table = {}
            for row in cur.fetchall():
                if isinstance(row, dict) or hasattr(row, "keys"):
                    row_dict = dict(row)
                elif hasattr(row, "_fields"):
                    row_dict = row._asdict()
                else:
                    row_dict = {"tbl_name": row[0], "latest": row[1], "total": row[2], "unique_syms": row[3]}
                results_by_table[row_dict["tbl_name"]] = (
                    row_dict["latest"],
                    row_dict["total"],
                    row_dict["unique_syms"],
                )

            for tbl, _col, max_days, sev in table_checks:
                try:
                    if tbl in results_by_table:
                        latest, _total, unique_syms = results_by_table[tbl]

                        if not latest:
                            self.log(
                                "fundamental_data",
                                WARN,
                                tbl,
                                f"{tbl} is empty",
                                {},
                            )
                        else:
                            if isinstance(latest, str):
                                latest = _date.fromisoformat(latest)
                            age = (today - latest).days
                            result_sev = sev if age > max_days else INFO
                            self.log(
                                "fundamental_data",
                                result_sev,
                                tbl,
                                f"{tbl} {age}d old ({unique_syms} symbols)",
                                {
                                    "latest": str(latest),
                                    "age_days": age,
                                    "symbols": unique_syms,
                                },
                            )
                except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                    self.log(
                        "fundamental_data",
                        WARN,
                        tbl,
                        f"Check skipped: {e}",
                        None,
                    )
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            logger.warning(f"Fundamental data checks failed: {e}")

    def check_derived_metrics(self, cur: Any) -> None:
        try:
            interval_7d = get_interval_sql("7d")
            # RSI bounds check (should be 0-100)
            cur.execute(f"""
                SELECT COUNT(*) FILTER (WHERE rsi < 0 OR rsi > 100) AS bad_rsi,
                       COUNT(*) FILTER (WHERE rsi IS NULL) AS null_rsi,
                       COUNT(*) AS total
                FROM technical_data_daily
                WHERE date >= CURRENT_DATE - {interval_7d}
            """)
            row = cur.fetchone()
            if row is None:
                raise ValueError("RSI bounds check query returned no results - database state corrupted")
            # BUG FOUND 2026-08-11: DictRow (what DictCursor actually returns) is dict-LIKE
            # but not a `dict` subclass - always raised on real data.
            if isinstance(row, dict) or hasattr(row, "keys"):
                bad_rsi, null_rsi, total = row.get("bad_rsi"), row.get("null_rsi"), row.get("total")
            else:
                raise TypeError(
                    f"Expected dict-like row from DictCursor, got {type(row).__name__}. "
                    f"This indicates cursor configuration mismatch. Check data_patrol cursor factory."
                )
            if bad_rsi is None or null_rsi is None or total is None:
                raise ValueError("COUNT(*) FILTER for RSI check returned NULL - cannot evaluate technical data quality")
            bad_rsi = int(bad_rsi)
            null_rsi = int(null_rsi)

            if bad_rsi > 0:
                self.log(
                    "derived_metrics",
                    ERROR,
                    "technical_data_daily",
                    f"{bad_rsi} rows with invalid RSI (<0 or >100)",
                    {"bad_rsi": bad_rsi, "total": total},
                )
            else:
                self.log(
                    "derived_metrics",
                    INFO,
                    "technical_data_daily",
                    f"RSI bounds valid ({total} rows)",
                    None,
                )

            # NaN/Infinity check
            cur.execute(f"""
                SELECT COUNT(*) FILTER (WHERE atr = 'NaN' OR atr = 'Infinity' OR atr = '-Infinity') AS bad_atr,
                       COUNT(*) FILTER (WHERE rsi = 'NaN' OR rsi = 'Infinity') AS bad_rsi_nan
                FROM technical_data_daily
                WHERE date >= CURRENT_DATE - {interval_7d}
            """)
            row = cur.fetchone()
            if row is None:
                raise ValueError("NaN check query returned no results - database state corrupted")
            bad_atr = row.get("bad_atr") if hasattr(row, "get") else row[0]
            bad_rsi_nan = row.get("bad_rsi_nan") if hasattr(row, "get") else row[1]
            if bad_atr is None or bad_rsi_nan is None:
                raise ValueError("COUNT(*) FILTER for NaN check returned NULL - cannot evaluate data quality")
            bad_atr = int(bad_atr)
            bad_rsi_nan = int(bad_rsi_nan)

            if bad_atr > 0 or bad_rsi_nan > 0:
                self.log(
                    "derived_metrics",
                    ERROR,
                    "technical_data_daily",
                    f"{bad_atr} NaN ATR, {bad_rsi_nan} NaN RSI (computation error)",
                    {"nan_count": bad_atr + bad_rsi_nan},
                )
            else:
                self.log(
                    "derived_metrics",
                    INFO,
                    "technical_data_daily",
                    "No NaN/Infinity values in technical data",
                    None,
                )
        except (
            psycopg2.DatabaseError,
            psycopg2.OperationalError,
            ValueError,
            ZeroDivisionError,
            TypeError,
        ) as e:
            self.log(
                "derived_metrics",
                ERROR,
                "technical_data_daily",
                f"Check failed: {e}",
                None,
            )

    def check_sentiment_aggregate(self, cur: Any) -> None:
        """Verify market_sentiment table and freshness.

        BUG FOUND 2026-08-11: this checked a table called "sentiment_aggregate" with columns
        "aggregate_sentiment"/"aaii_bullish"/"naaim_bullish" that have never existed anywhere
        in this schema (confirmed against information_schema.tables - zero rows returned, not
        an error, so this silently reported "Missing columns" as an ERROR on every single run
        since whenever this check was written, never once validating real data). The real,
        live table for this concept is `market_sentiment` (VIX, put/call, fear/greed,
        bullish/bearish/neutral %, sentiment_score - 21 rows and actively written) - it was not
        monitored by any other check (aaii_sentiment, a separate real table, already has its
        own dedicated staleness check in staleness.py). Repointed at the real table/columns
        instead of guessing a rename for columns that were never real.
        """
        try:
            # Check table structure
            cur.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'market_sentiment'
                ORDER BY column_name
            """)
            columns = []
            for row in cur.fetchall():
                if isinstance(row, dict) or hasattr(row, "keys"):
                    col = row.get("column_name")
                else:
                    raise TypeError(
                        f"Expected dict-like row from DictCursor, got {type(row).__name__}. "
                        f"This indicates cursor configuration mismatch. Check data_patrol cursor factory."
                    )
                if col:
                    columns.append(col)

            required_cols = {
                "date",
                "sentiment_score",
                "bullish_pct",
                "bearish_pct",
                "updated_at",
            }
            present_cols = set(columns)

            if required_cols.issubset(present_cols):
                self.log(
                    "sentiment_aggregate",
                    INFO,
                    "market_sentiment",
                    f"Table structure valid ({len(columns)} columns)",
                    {"columns": columns},
                )
            else:
                missing = required_cols - present_cols
                self.log(
                    "sentiment_aggregate",
                    ERROR,
                    "market_sentiment",
                    f"Missing columns: {', '.join(missing)}",
                    {"missing": list(missing)},
                )
                return

            # Check data freshness
            cur.execute("SELECT MAX(date) AS max_date, MAX(updated_at) AS max_updated FROM market_sentiment")
            row = cur.fetchone()
            if row:
                max_date = row.get("max_date") if hasattr(row, "get") else row[0]
                max_updated = row.get("max_updated") if hasattr(row, "get") else row[1]
            else:
                max_date = max_updated = None

            if not max_date:
                self.log(
                    "sentiment_aggregate",
                    WARN,
                    "market_sentiment",
                    "No data in market_sentiment table",
                    {},
                )
            else:
                if isinstance(max_date, str):
                    max_date = _date.fromisoformat(max_date)
                if isinstance(max_updated, str):
                    max_updated = datetime.fromisoformat(max_updated)
                age = (_date.today() - max_date).days
                updated_age = (datetime.now(timezone.utc) - max_updated).total_seconds() / 3600
                sev = WARN if age > 7 else INFO
                self.log(
                    "sentiment_aggregate",
                    sev,
                    "market_sentiment",
                    f"Latest data: {max_date} ({age}d old), updated {updated_age:.1f}h ago",
                    {
                        "data_date": str(max_date),
                        "age_days": age,
                        "updated_hours": round(updated_age, 1),
                    },
                )
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            self.log(
                "sentiment_aggregate",
                WARN,
                "market_sentiment",
                f"Check skipped: {e}",
                None,
            )

    def check_trade_recorder_columns(self, cur: Any) -> None:
        """Verify algo_trades and algo_positions table structure."""
        tables = [
            (
                "algo_trades",
                {
                    "symbol",
                    "entry_date",
                    "entry_price",
                    "quantity",
                    "signal_type",
                    "exit_date",
                    "exit_price",
                    "pnl",
                },
            ),
            (
                "algo_positions",
                {
                    "symbol",
                    "entry_date",
                    "entry_price",
                    "current_price",
                    "quantity",
                    "status",
                    "updated_at",
                },
            ),
        ]

        for tbl, required_cols in tables:
            try:
                tbl_safe = assert_safe_table(tbl)
                cur.execute(
                    """
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name = %s
                    ORDER BY column_name
                """,
                    (tbl,),
                )
                columns = []
                for row in cur.fetchall():
                    # BUG FOUND 2026-08-11: DictRow is dict-LIKE but not a `dict` subclass.
                    if isinstance(row, dict) or hasattr(row, "keys"):
                        col = row.get("column_name")
                    else:
                        raise TypeError(
                            f"Expected dict-like row from DictCursor, got {type(row).__name__}. "
                            f"This indicates cursor configuration mismatch. Check data_patrol cursor factory."
                        )
                    if col:
                        columns.append(col)
                present_cols = set(columns)

                if required_cols.issubset(present_cols):
                    self.log(
                        "trade_recorder_columns",
                        INFO,
                        tbl,
                        f"Table structure valid ({len(columns)} columns)",
                        {"columns": columns},
                    )

                    # Check data freshness (use updated_at if created_at doesn't exist)
                    # First try created_at, fallback to updated_at
                    try:
                        cur.execute(f"SELECT COUNT(*) as count, MAX(created_at) as max_updated FROM {tbl_safe}")
                    except psycopg2.DatabaseError:
                        # Fallback to updated_at if created_at doesn't exist
                        cur.execute(f"SELECT COUNT(*) as count, MAX(updated_at) as max_updated FROM {tbl_safe}")
                    row = cur.fetchone()
                    # BUG FOUND 2026-08-11: DictRow is dict-LIKE but not a `dict` subclass.
                    if isinstance(row, dict) or hasattr(row, "keys"):
                        count, max_updated = row.get("count"), row.get("max_updated")
                    else:
                        raise TypeError(
                            f"Expected dict-like row from DictCursor, got {type(row).__name__}. "
                            f"This indicates cursor configuration mismatch. Check data_patrol cursor factory."
                        )

                    if count is not None and count > 0 and max_updated:
                        now = datetime.now(timezone.utc) if max_updated.tzinfo else datetime.now()
                        updated_age = (now - max_updated).total_seconds() / 3600
                        self.log(
                            "trade_recorder_watermark",
                            INFO,
                            tbl,
                            f"{count} records, last updated {updated_age:.1f}h ago",
                            {
                                "record_count": count,
                                "updated_hours": round(updated_age, 1),
                            },
                        )
                else:
                    missing = required_cols - present_cols
                    self.log(
                        "trade_recorder_columns",
                        ERROR,
                        tbl,
                        f"Missing columns: {', '.join(missing)}",
                        {"missing": list(missing)},
                    )
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                self.log(
                    "trade_recorder_columns",
                    WARN,
                    tbl,
                    f"Check skipped: {e}",
                    None,
                )
