#!/usr/bin/env python3
"""Specialized data checks - earnings, fundamentals, derivatives, sentiment."""

import logging
from datetime import date as _date
from datetime import datetime, timezone
from typing import Any

import psycopg2

from utils.db import assert_safe_column, assert_safe_table

from ..base import BaseCheck, CheckResult
from ..config import ERROR, INFO, WARN

logger = logging.getLogger(__name__)


class SpecializedChecker(BaseCheck):
    """Check specialized data tables: earnings, fundamentals, technical indicators."""

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
            except Exception:
                pass
            try:
                fn(cur)
            except Exception as e:
                logger.error(f"Specialized {fn_name} failed: {e}")
            finally:
                try:
                    cur.execute(f"ROLLBACK TO SAVEPOINT {sp}")
                except Exception:
                    pass

        return self.results

    def check_earnings_data(self, cur: Any) -> None:
        """Check earnings data freshness and coverage."""
        today = _date.today()
        sources = [
            ("earnings_estimates", ["date_recorded", "date_range"], 7, WARN),
            ("earnings_estimate_revisions", ["date_recorded", "date_range"], 14, WARN),
            ("earnings_history", ["earnings_date", "quarter"], 120, WARN),
        ]

        for tbl, col_options, max_days, sev in sources:
            try:
                col = col_options[0]
                tbl_safe = assert_safe_table(tbl)
                cur.execute(f"""
                    SELECT COUNT(*), MAX({col}::date) as latest
                    FROM {tbl_safe}
                """)
                result = cur.fetchone()
                count, latest = result[0], result[1]

                if not latest:
                    self.log(
                        "earnings_staleness",
                        WARN,
                        tbl,
                        f"{tbl} is empty",
                        {"count": 0},
                    )
                else:
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
                self.log(
                    "earnings_staleness",
                    INFO,
                    tbl,
                    f"Check skipped (table may not exist): {e}",
                    None,
                )

        # Check earnings coverage
        try:
            cur.execute("""
                SELECT
                    COUNT(DISTINCT e.symbol) AS est_syms,
                    COUNT(DISTINCT p.symbol) AS price_syms
                FROM price_daily p
                LEFT JOIN earnings_estimates e
                    ON e.symbol = p.symbol
                   AND e.created_at >= CURRENT_DATE - INTERVAL '7 days'
                WHERE p.date >= CURRENT_DATE - INTERVAL '7 days'
            """)
            est_syms, price_syms = cur.fetchone()
            est_syms = int(est_syms or 0)
            price_syms = int(price_syms or 1)
            pct = est_syms / price_syms * 100
            sev = WARN if pct < 80 else INFO
            self.log(
                "earnings_coverage",
                sev,
                "earnings_estimates",
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
            self.log(
                "earnings_coverage",
                WARN,
                "earnings_estimates",
                f"Check skipped: {e}",
                None,
            )

    def check_fundamental_data(self, cur: Any) -> None:
        """Check fundamental data freshness."""
        today = _date.today()
        table_checks = [
            ("quarterly_income_statement", "created_at", 45, WARN),
            ("quarterly_balance_sheet", "created_at", 45, WARN),
            ("quarterly_cash_flow", "created_at", 45, WARN),
            ("annual_income_statement", "created_at", 120, WARN),
            ("annual_balance_sheet", "created_at", 120, WARN),
            ("annual_cash_flow", "created_at", 120, WARN),
            ("key_metrics", "created_at", 14, WARN),
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
                row_dict = dict(row)
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
        """Check technical indicators for bounds violations."""
        try:
            # RSI bounds check (should be 0-100)
            cur.execute("""
                SELECT COUNT(*) FILTER (WHERE rsi < 0 OR rsi > 100) AS bad_rsi,
                       COUNT(*) FILTER (WHERE rsi IS NULL) AS null_rsi,
                       COUNT(*) AS total
                FROM technical_data_daily
                WHERE date >= CURRENT_DATE - INTERVAL '7 days'
            """)
            bad_rsi, null_rsi, total = cur.fetchone()
            bad_rsi = int(bad_rsi or 0)
            null_rsi = int(null_rsi or 0)

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
            cur.execute("""
                SELECT COUNT(*) FILTER (WHERE atr = 'NaN' OR atr = 'Infinity' OR atr = '-Infinity') AS bad_atr,
                       COUNT(*) FILTER (WHERE rsi = 'NaN' OR rsi = 'Infinity') AS bad_rsi_nan
                FROM technical_data_daily
                WHERE date >= CURRENT_DATE - INTERVAL '7 days'
            """)
            bad_atr, bad_rsi_nan = cur.fetchone()
            bad_atr = int(bad_atr or 0)
            bad_rsi_nan = int(bad_rsi_nan or 0)

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
        """Verify sentiment_aggregate table and freshness."""
        try:
            # Check table structure
            cur.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'sentiment_aggregate'
                ORDER BY column_name
            """)
            columns = [row[0] for row in cur.fetchall()]

            required_cols = {
                "date",
                "aggregate_sentiment",
                "aaii_bullish",
                "naaim_bullish",
                "updated_at",
            }
            present_cols = set(columns)

            if required_cols.issubset(present_cols):
                self.log(
                    "sentiment_aggregate",
                    INFO,
                    "sentiment_aggregate",
                    f"Table structure valid ({len(columns)} columns)",
                    {"columns": columns},
                )
            else:
                missing = required_cols - present_cols
                self.log(
                    "sentiment_aggregate",
                    ERROR,
                    "sentiment_aggregate",
                    f"Missing columns: {', '.join(missing)}",
                    {"missing": list(missing)},
                )
                return

            # Check data freshness
            cur.execute("SELECT MAX(date), MAX(updated_at) FROM sentiment_aggregate")
            max_date, max_updated = cur.fetchone()

            if not max_date:
                self.log(
                    "sentiment_aggregate",
                    WARN,
                    "sentiment_aggregate",
                    "No data in sentiment_aggregate table",
                    {},
                )
            else:
                age = (_date.today() - max_date).days
                updated_age = (datetime.now(timezone.utc) - max_updated).total_seconds() / 3600
                sev = WARN if age > 7 else INFO
                self.log(
                    "sentiment_aggregate",
                    sev,
                    "sentiment_aggregate",
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
                "sentiment_aggregate",
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
                columns = [row[0] for row in cur.fetchall()]
                present_cols = set(columns)

                if required_cols.issubset(present_cols):
                    self.log(
                        "trade_recorder_columns",
                        INFO,
                        tbl,
                        f"Table structure valid ({len(columns)} columns)",
                        {"columns": columns},
                    )

                    # Check data freshness
                    cur.execute(f"SELECT COUNT(*), MAX(created_at) FROM {tbl_safe}")
                    count, max_updated = cur.fetchone()

                    if count > 0 and max_updated:
                        updated_age = (datetime.now(timezone.utc) - max_updated).total_seconds() / 3600
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
