#!/usr/bin/env python3
"""Data alignment checks - cross-table validation, signal alignment, coverage."""

import logging

import psycopg2

from utils.db import assert_safe_table

from ..base import BaseCheck, CheckResult
from ..config import ERROR, INFO, WARN


logger = logging.getLogger(__name__)


class AlignmentChecker(BaseCheck):
    """Check alignment and consistency across tables."""

    def run(self, cur) -> list[CheckResult]:
        """Execute all alignment checks."""
        self.results = []

        self.check_signal_source_alignment(cur)
        self.check_signal_data_alignment(cur)
        self.check_trade_alignment(cur)
        self.check_score_freshness(cur)
        self.check_cross_table_alignment(cur)

        return self.results

    def check_signal_source_alignment(self, cur) -> None:
        """Cross-validate SQS with its input tables."""
        try:
            cur.execute("SELECT MAX(date) FROM signal_quality_scores")
            row = cur.fetchone()
            sqs_date = row[0] if row and row[0] is not None else None
            if not sqs_date:
                self.log(
                    "alignment",
                    INFO,
                    "signal_quality_scores",
                    "No signal_quality_scores data yet",
                    None,
                )
                return

            cur.execute("SELECT MAX(date) FROM buy_sell_daily WHERE date <= %s", (sqs_date,))
            row = cur.fetchone()
            buy_sell_date = row[0] if row and row[0] is not None else None

            if not buy_sell_date or buy_sell_date < sqs_date:
                self.log(
                    "alignment",
                    WARN,
                    "buy_sell_daily",
                    f"buy_sell_daily ({buy_sell_date}) older than signal_quality_scores ({sqs_date})",
                    {"sqs_date": str(sqs_date), "buy_sell_date": str(buy_sell_date)},
                )
                return

            # Check symbol alignment
            cur.execute(
                """
                SELECT
                    (SELECT COUNT(DISTINCT symbol) FROM signal_quality_scores WHERE date = %s) AS sqs_count,
                    (SELECT COUNT(DISTINCT symbol) FROM buy_sell_daily WHERE date = %s) AS buy_sell_count
            """,
                (sqs_date, sqs_date),
            )
            sqs_count, buy_sell_count = cur.fetchone()

            if buy_sell_count == 0:
                self.log(
                    "alignment",
                    ERROR,
                    "buy_sell_daily",
                    f"buy_sell_daily has 0 symbols on {sqs_date} (SQS has {sqs_count})",
                    {"sqs_count": sqs_count, "buy_sell_count": 0},
                )
            elif buy_sell_count < sqs_count:
                coverage_pct = (buy_sell_count / sqs_count * 100) if sqs_count else 0
                self.log(
                    "alignment",
                    WARN,
                    "buy_sell_daily",
                    f"buy_sell_daily coverage {coverage_pct:.1f}% ({buy_sell_count}/{sqs_count} symbols)",
                    {
                        "buy_sell_count": buy_sell_count,
                        "sqs_count": sqs_count,
                        "coverage_pct": round(coverage_pct, 1),
                    },
                )
            else:
                self.log(
                    "alignment",
                    INFO,
                    "signal_quality_scores",
                    f"Sources aligned: {buy_sell_count} symbols in both tables",
                    {"sqs_count": sqs_count, "buy_sell_count": buy_sell_count},
                )
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            self.log("alignment", ERROR, "signal_alignment", f"Check failed: {e}", None)

    def check_signal_data_alignment(self, cur) -> None:
        """Every BUY/SELL signal must have matching price + technical data."""
        try:
            cur.execute("""
                SELECT COUNT(*) FILTER (WHERE signal_type IN ('BUY', 'SELL')) AS total_signals,
                       COUNT(*) FILTER (
                           WHERE signal_type IN ('BUY', 'SELL')
                             AND NOT EXISTS (
                                 SELECT 1 FROM price_daily pd
                                 WHERE pd.symbol = buy_sell_daily.symbol
                                   AND pd.date = buy_sell_daily.date
                             )
                       ) AS missing_price,
                       COUNT(*) FILTER (
                           WHERE signal_type IN ('BUY', 'SELL')
                             AND NOT EXISTS (
                                 SELECT 1 FROM technical_data_daily td
                                 WHERE td.symbol = buy_sell_daily.symbol
                                   AND td.date = buy_sell_daily.date
                             )
                       ) AS missing_tech
                FROM buy_sell_daily
                WHERE date >= CURRENT_DATE - INTERVAL '14 days'
            """)
            total, missing_price, missing_tech = cur.fetchone()
            total = int(total or 0)
            missing_price = int(missing_price or 0)
            missing_tech = int(missing_tech or 0)

            if missing_price > 0 or missing_tech > 0:
                self.log(
                    "signal_alignment",
                    ERROR,
                    "buy_sell_daily",
                    f"{missing_price} signals missing price_daily, {missing_tech} missing technical_data",
                    {
                        "total_signals": total,
                        "missing_price": missing_price,
                        "missing_tech": missing_tech,
                    },
                )
            else:
                self.log(
                    "signal_alignment",
                    INFO,
                    "buy_sell_daily",
                    f"All {total} signals have matching price + technical data",
                    None,
                )
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            self.log("signal_alignment", ERROR, "buy_sell_daily", f"Check failed: {e}", None)

    def check_trade_alignment(self, cur) -> None:
        """Every filled trade must have price history on/after fill date."""
        try:
            cur.execute("""
                SELECT t.trade_id, t.symbol, t.created_at::date as fill_date, COUNT(p.date) as price_count
                FROM algo_trades t
                LEFT JOIN price_daily p
                    ON t.symbol = p.symbol
                   AND p.date >= t.created_at::date
                   AND p.date <= CURRENT_DATE
                WHERE t.status IN ('open', 'pending')
                  AND t.created_at >= CURRENT_DATE - INTERVAL '60 days'
                GROUP BY t.trade_id, t.symbol, fill_date
                HAVING COUNT(p.date) = 0
            """)
            orphaned = cur.fetchall()

            if orphaned:
                self.log(
                    "trade_alignment",
                    ERROR,
                    "algo_trades/price_daily",
                    f"{len(orphaned)} filled trades missing price history",
                    {
                        "orphaned_trades": len(orphaned),
                        "sample": [{"trade_id": r[0], "symbol": r[1], "fill_date": str(r[2])} for r in orphaned[:5]],
                    },
                )
            else:
                self.log(
                    "trade_alignment",
                    INFO,
                    "algo_trades/price_daily",
                    "All recent filled trades have price history",
                    None,
                )
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            self.log(
                "trade_alignment",
                INFO,
                "algo_trades/price_daily",
                f"Check skipped (table may not exist): {e}",
                None,
            )

    def check_score_freshness(self, cur) -> None:
        """Computed scores should be updated AFTER raw data."""
        try:
            cur.execute("""
                SELECT
                    (SELECT MAX(date) FROM price_daily) AS price_latest,
                    (SELECT MAX(date) FROM trend_template_data) AS trend_latest,
                    (SELECT MAX(date) FROM signal_quality_scores) AS sqs_latest
            """)
            price_d, trend_d, sqs_d = cur.fetchone()

            for name, comp_date in [
                ("trend_template_data", trend_d),
                ("signal_quality_scores", sqs_d),
            ]:
                if comp_date and price_d:
                    if comp_date < price_d:
                        lag_days = (price_d - comp_date).days
                        self.log(
                            "score_freshness",
                            WARN,
                            name,
                            f"{name} ({comp_date}) older than price_daily ({price_d}) by {lag_days} days",
                            {"lag_days": lag_days},
                        )
                    else:
                        self.log(
                            "score_freshness",
                            INFO,
                            name,
                            f"{name} aligned with price data",
                            None,
                        )
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            self.log(
                "score_freshness",
                ERROR,
                "computed_scores",
                f"Check failed: {e}",
                None,
            )

    def check_cross_table_alignment(self, cur) -> None:
        """Dependent tables cover same symbol universe as price_daily."""
        try:
            cur.execute("""
                SELECT COUNT(DISTINCT symbol) FROM price_daily
                WHERE date = (SELECT MAX(date) FROM price_daily)
            """)
            row = cur.fetchone()
            baseline = int(row[0]) if row and row[0] is not None else 1
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            self.log(
                "cross_align",
                WARN,
                "price_daily",
                f"Baseline query failed: {e}",
                None,
            )
            return

        checks = [
            (
                "technical_data_daily",
                "date = (SELECT MAX(date) FROM technical_data_daily)",
                0.95,
                ERROR,
            ),
            (
                "buy_sell_daily",
                "date = (SELECT MAX(date) FROM buy_sell_daily)",
                0.90,
                ERROR,
            ),
            (
                "trend_template_data",
                "date = (SELECT MAX(date) FROM trend_template_data)",
                0.95,
                WARN,
            ),
            (
                "signal_quality_scores",
                "date = (SELECT MAX(date) FROM signal_quality_scores)",
                0.95,
                WARN,
            ),
            ("stock_scores", "1=1", 0.90, WARN),
        ]

        try:
            for tbl, _where, _min_ratio, _sev in checks:
                assert_safe_table(tbl)

            union_parts = []
            for tbl, where, _min_ratio, _sev in checks:
                tbl_safe = assert_safe_table(tbl)
                union_parts.append(
                    f"SELECT '{tbl}' as tbl_name, COUNT(DISTINCT symbol) as cnt FROM {tbl_safe} WHERE {where}"
                )

            union_query = " UNION ALL ".join(union_parts)
            cur.execute(union_query)

            counts_by_table = {}
            for row in cur.fetchall():
                row_dict = dict(row)
                counts_by_table[row_dict["tbl_name"]] = row_dict["cnt"] or 0

            for tbl, _where, min_ratio, sev in checks:
                try:
                    count = counts_by_table.get(tbl, 0)
                    ratio = count / baseline
                    if ratio < min_ratio:
                        self.log(
                            "cross_align",
                            sev,
                            tbl,
                            f"{tbl} coverage {ratio * 100:.1f}% < {min_ratio * 100:.0f}% ({count}/{baseline} symbols)",
                            {"coverage_pct": round(ratio * 100, 1), "baseline": baseline},
                        )
                    else:
                        self.log(
                            "cross_align",
                            INFO,
                            tbl,
                            f"{tbl} alignment OK ({ratio * 100:.1f}%)",
                            None,
                        )
                except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
                    self.log("cross_align", WARN, tbl, f"Check skipped: {e}", None)
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            self.log("cross_align", ERROR, "alignment", f"Cross-alignment check failed: {e}", None)
