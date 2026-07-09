#!/usr/bin/env python3
"""Coverage and loader contract checks."""

import logging
from typing import Any

import psycopg2

from utils.db import assert_safe_table, safe_select_count

from ..base import BaseCheck, CheckResult
from ..config import ERROR, INFO, WARN

logger = logging.getLogger(__name__)


class CoverageChecker(BaseCheck):
    """Check symbol coverage and loader contracts."""

    def run(self, cur: Any) -> list[CheckResult]:
        """Execute coverage checks."""
        self.results = []

        self.check_universe_coverage(cur)
        self.check_loader_coverage(cur)
        self.check_loader_contracts(cur)
        self.check_signal_quality_ratio(cur)

        return self.results

    def check_universe_coverage(self, cur: Any) -> None:
        """Check % symbols updated today (catches loader drop-offs)."""
        try:
            cur.execute("""
                WITH latest_date AS (
                    SELECT MAX(date) AS max_date FROM price_daily
                )
                SELECT
                    COUNT(DISTINCT CASE WHEN pd.date = ld.max_date THEN pd.symbol END) AS today_count,
                    COUNT(DISTINCT pd.symbol) AS total_count
                FROM price_daily pd
                CROSS JOIN latest_date ld
            """)
            today_count, total_count = cur.fetchone()
            if today_count is None:
                raise ValueError("price_daily today_count returned NULL — loader may be stalled or corrupted")
            if total_count is None:
                raise ValueError("price_daily total_count returned NULL — loader may be stalled")
            today_count = int(today_count)
            total_count = int(total_count)
            if total_count <= 0:
                logger.warning("price_daily total_count is 0 — skipping coverage check (no expected records)")
                return
            pct = today_count / total_count * 100

            if pct < 0.1:
                self.log(
                    "coverage",
                    WARN,
                    "price_daily",
                    f"Only {pct:.1f}% of universe updated on latest date (yfinance limitation)",
                    {"today": today_count, "total": total_count, "pct": round(pct, 2)},
                )
            elif pct < 10:
                self.log(
                    "coverage",
                    INFO,
                    "price_daily",
                    f"{pct:.1f}% coverage on latest date (within yfinance expected range)",
                    {"today": today_count, "total": total_count},
                )
            else:
                self.log(
                    "coverage",
                    INFO,
                    "price_daily",
                    f"{pct:.1f}% universe coverage",
                    None,
                )
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            self.log("coverage", ERROR, "price_daily", f"Check failed: {e}", None)

    def check_loader_coverage(self, cur: Any) -> None:
        """Verify symbol coverage >= threshold for critical loaders."""
        try:
            cov_cfg = self.config.get_coverage_thresholds()
            coverage_error_pct = cov_cfg["error_pct"]
            coverage_warn_pct = cov_cfg["warn_pct"]

            cur.execute("SELECT COUNT(*) FROM stock_symbols WHERE active = true")
            row = cur.fetchone()
            if row is None or row[0] is None:
                raise ValueError("Expected symbol count query returned NULL — cannot validate loader coverage")
            expected_count = int(row[0])

            if expected_count == 0:
                self.log(
                    "coverage",
                    ERROR,
                    "stock_symbols",
                    "No active symbols in stock_symbols table — cannot calculate loader coverage percentages",
                    {"expected_count": 0},
                )
                return

            critical_tables = [
                "price_daily",
                "technical_data_daily",
                "buy_sell_daily",
                "trend_template_data",
                "signal_quality_scores",
            ]

            try:
                for table_name in critical_tables:
                    assert_safe_table(table_name)

                union_parts = []
                for table_name in critical_tables:
                    union_parts.append(f"""
                        SELECT '{table_name}' as table_name, COUNT(DISTINCT symbol) as cnt
                        FROM {assert_safe_table(table_name)}
                        WHERE date = (SELECT MAX(date) FROM {assert_safe_table(table_name)})
                    """)

                union_query = " UNION ALL ".join(union_parts)
                cur.execute(union_query)

                results_by_table = {}
                for row in cur.fetchall():
                    row_dict = dict(row)
                    table_name = row_dict["table_name"]
                    cnt = row_dict["cnt"]
                    if cnt is None:
                        raise ValueError(
                            f"COUNT(DISTINCT symbol) returned NULL for {table_name} — table may be empty or query failed"
                        )
                    results_by_table[table_name] = int(cnt)

                # Verify all critical tables are represented
                missing_tables = set(critical_tables) - set(results_by_table.keys())
                if missing_tables:
                    raise ValueError(f"Coverage query missing tables: {missing_tables} — UNION query may have failed")

                for table_name in critical_tables:
                    try:
                        table_count = results_by_table[table_name]
                        if expected_count <= 0:
                            logger.warning(f"{table_name} expected_count is 0 — skipping coverage check")
                            continue
                        coverage_pct = table_count / expected_count * 100

                        if coverage_pct < coverage_error_pct:
                            self.log(
                                "coverage",
                                ERROR,
                                table_name,
                                f"{table_name} coverage {coverage_pct:.1f}% < {coverage_error_pct}% threshold ({table_count}/{expected_count} symbols)",
                                {
                                    "coverage_pct": round(coverage_pct, 1),
                                    "count": table_count,
                                    "expected": expected_count,
                                    "threshold": coverage_error_pct,
                                },
                            )
                        elif coverage_pct < coverage_warn_pct:
                            self.log(
                                "coverage",
                                WARN,
                                table_name,
                                f"{table_name} coverage {coverage_pct:.1f}% < {coverage_warn_pct}% warn threshold",
                                {
                                    "coverage_pct": round(coverage_pct, 1),
                                    "count": table_count,
                                    "expected": expected_count,
                                },
                            )
                        else:
                            self.log(
                                "coverage",
                                INFO,
                                table_name,
                                f"{table_name} coverage {coverage_pct:.1f}% OK",
                                {
                                    "coverage_pct": round(coverage_pct, 1),
                                    "count": table_count,
                                },
                            )
                    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                        self.log("coverage", ERROR, table_name, f"Check failed: {e}", None)
            except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                self.log(
                    "coverage",
                    ERROR,
                    "patrol_coverage",
                    f"Union query check failed: {e}",
                    None,
                )
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            self.log(
                "coverage",
                ERROR,
                "patrol_coverage",
                f"Coverage check failed: {e}",
                None,
            )

    def check_loader_contracts(self, cur: Any) -> None:
        """Verify per-loader output contracts."""
        contracts = self.config.get_loader_contracts()

        for tbl, contract in contracts.items():
            sp = f"sp_contract_{tbl}"
            cur.execute(f"SAVEPOINT {sp}")
            try:
                tbl_safe = assert_safe_table(tbl)
                actual, _ = safe_select_count(cur, tbl_safe, where_clause=contract["condition"])
                expected = contract["min_rows"]
                severity = contract["severity"]

                if actual < expected:
                    self.log(
                        "loader_contract",
                        severity,
                        tbl,
                        f"{actual:,} rows < {expected:,} expected ({contract['description']})",
                        {"actual": actual, "expected": expected},
                    )
                else:
                    self.log(
                        "loader_contract",
                        INFO,
                        tbl,
                        f"{actual:,} rows OK",
                        None,
                    )
            except Exception as e:
                self.log("loader_contract", ERROR, tbl, f"Check failed: {e}", None)
                cur.execute(f"ROLLBACK TO SAVEPOINT {sp}")
            finally:
                cur.execute(f"RELEASE SAVEPOINT {sp}")

    def check_signal_quality_ratio(self, cur: Any) -> None:
        """Check buy_sell_daily signal cleanness."""
        try:
            cur.execute("""
                SELECT
                    COUNT(*) FILTER (WHERE signal_type IN ('BUY', 'SELL')) AS clean,
                    COUNT(*) AS total
                FROM buy_sell_daily
                WHERE date >= CURRENT_DATE - get_interval_sql('30d')
            """)
            row = cur.fetchone()
            if row and row[1] > 0:
                clean_pct = (row[0] / row[1]) * 100
                # EXPLICIT THRESHOLD: buy_sell_daily signals must be ≥80% clean (not NULL)
                # This is a fixed contract, not a configurable setting
                threshold = 80
                if clean_pct < threshold:
                    self.log(
                        "contract_signal_quality",
                        ERROR,
                        "buy_sell_daily",
                        f"Only {clean_pct:.1f}% clean BUY/SELL signals ({row[1] - row[0]} NULL/None of {row[1]} total)",
                        {"clean_pct": clean_pct},
                    )
                else:
                    self.log(
                        "contract_signal_quality",
                        INFO,
                        "buy_sell_daily",
                        f"{clean_pct:.1f}% clean BUY/SELL signals",
                        None,
                    )
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            self.log(
                "contract_signal_quality",
                ERROR,
                "buy_sell_daily",
                f"Failed: {e}",
                None,
            )
