#!/usr/bin/env python3
"""Earnings Metrics Loader - trailing-4-quarter EPS consistency score.

GOVERNANCE 2026-08-19 (goal: "no SEC data"/missing factor inputs audit): earnings_metrics
was, until this loader existed, populated exactly once by migration 1147 and never again -
every single row shared the identical 2026-08-09 timestamp, confirmed live via
`SELECT MIN(created_at), MAX(created_at) FROM earnings_metrics` returning the same instant
for all 5,119 rows. No entry in data_loader_status, no loader script anywhere referenced
this table (`grep -rl earnings_metrics loaders/` returned nothing) - the table was never
wired into the ongoing pipeline at all, only a one-time backfill. Real quarterly EPS data
kept refreshing underneath it via quarterly_income_statement, but this table's score never
moved to reflect it - a frozen snapshot masquerading as a live factor on the scores
dashboard's "Earnings" tab.

Reuses the exact same formula migration 1147 introduced (see that file's own docstring for
the full rationale on why this simpler EPS-consistency proxy replaced the originally-
envisioned beat/miss-rate design: analyst_quarterly_estimates and earnings_history are both
real tables with zero loaders ever populating them, so a beat-rate score isn't computable
yet), just as a real, recurring per-symbol loader instead of a one-off migration:

- consistency_score = % of the trailing (up to) 4 reported quarters with positive EPS
- earnings_quality_score = consistency_score dampened by relative EPS volatility
  (stdev/|mean|, capped so it can only reduce the score, never invert its sign)

Run:
    python3 loaders/load_earnings_metrics.py [--symbols AAPL,MSFT]
"""

import logging
import sys
from datetime import date, datetime, timezone
from typing import Any

from loaders.runner import run_loader
from utils.db.context import DatabaseContext
from utils.optimal_loader import OptimalLoader

logger = logging.getLogger(__name__)


class EarningsMetricsLoader(OptimalLoader):
    """Trailing-4-quarter EPS consistency score, computed from quarterly_income_statement.

    GOVERNANCE: Derived entirely from our own already-loaded SEC quarterly filings data -
    no external API calls, no fallbacks/estimates. A symbol with fewer than 2 quarters of
    reported EPS on file is honestly marked unavailable, never defaulted to a guessed score.
    """

    table_name = "earnings_metrics"
    primary_key = ("symbol", "report_date")
    watermark_field = "updated_at"
    exclude_etfs_from_symbols = True

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Compute trailing-4-quarter EPS consistency for one symbol.

        since is unused - this is a derived snapshot recomputed fresh each run from
        whatever quarterly EPS history currently exists (mirrors quality_metrics/
        growth_metrics/value_metrics, which are also always-recompute derived metrics,
        not a true incremental feed).
        """
        now = datetime.now(timezone.utc)
        today = date.today()

        with DatabaseContext("read") as cur:
            cur.execute(
                """
                SELECT fiscal_year, fiscal_quarter, earnings_per_share
                FROM quarterly_income_statement
                WHERE symbol = %s AND earnings_per_share IS NOT NULL
                ORDER BY fiscal_year DESC, fiscal_quarter DESC
                LIMIT 4
                """,
                (symbol,),
            )
            rows = cur.fetchall()

        if len(rows) < 2:
            return [
                {
                    "symbol": symbol,
                    "report_date": today,
                    "earnings_quality_score": None,
                    "consistency_score": None,
                    "data_unavailable": True,
                    "unavailable_reason": "insufficient_quarterly_eps_history",
                    "created_at": now,
                    "updated_at": now,
                }
            ]

        eps_values = [float(r[2]) for r in rows]
        n_quarters = len(eps_values)
        positive_quarters = sum(1 for v in eps_values if v > 0)
        avg_eps = sum(eps_values) / n_quarters

        if n_quarters >= 2:
            variance = sum((v - avg_eps) ** 2 for v in eps_values) / (n_quarters - 1)
            stdev_eps = variance**0.5
        else:
            stdev_eps = 0.0

        consistency_score = round((positive_quarters / n_quarters) * 100, 2)

        volatility_dampener = min(1.0, (stdev_eps / abs(avg_eps)) / 2) if avg_eps != 0 else 0.0
        earnings_quality_score = round(min(100.0, max(0.0, consistency_score * (1 - volatility_dampener))), 2)

        return [
            {
                "symbol": symbol,
                "report_date": today,
                "earnings_quality_score": earnings_quality_score,
                "consistency_score": consistency_score,
                "data_unavailable": False,
                "unavailable_reason": None,
                "created_at": now,
                "updated_at": now,
            }
        ]


def main() -> int:
    """Run the earnings metrics loader."""
    try:
        return run_loader(EarningsMetricsLoader)
    except Exception as e:
        logger.error(f"[EARNINGS_METRICS FATAL] Loader crashed: {type(e).__name__}: {str(e)[:500]}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
