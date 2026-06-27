#!/usr/bin/env python3
"""Breadth 200-day moving average factor strategy for market exposure calculation."""

import logging
from typing import Any

from psycopg2 import sql as pgsql

from algo.risk.market_factor_strategy import MarketFactorStrategy

logger = logging.getLogger(__name__)


class Breadth200DMAFactor(MarketFactorStrategy):
    """Long-term breadth factor: % stocks above 200-day MA.

    Measures market participation in the long-term uptrend (monthly to quarterly).
    Weight: 10 points
    """

    @property
    def name(self) -> str:
        return "breadth_200dma"

    @property
    def weight(self) -> float:
        return 10.0  # 10 out of 100 total weight

    def calculate(self, eval_date: Any, cur: Any) -> dict[str, Any]:
        """Calculate % of stocks trading above 200-day MA.

        Scoring (linear):
        - 80%+ above 200-DMA = 100 (strong long-term participation)
        - 55% above 200-DMA = 50 (neutral)
        - 30% above 200-DMA = 0 (weak long-term participation)
        - <30% above 200-DMA = 0 (bearish regime)

        Raises ValueError if breadth data unavailable.
        """
        col = pgsql.Identifier("price_above_sma200")
        try:
            cur.execute(
                pgsql.SQL("""
                SELECT
                    COUNT(*) FILTER (WHERE {} = TRUE)  AS above,
                    COUNT(*) FILTER (WHERE {} IS NOT NULL) AS total
                FROM (
                    SELECT DISTINCT ON (symbol) {}
                    FROM trend_template_data
                    WHERE date <= %s AND date >= %s::date - INTERVAL '7 days'
                    ORDER BY symbol, date DESC
                ) latest
                """).format(col, col, col),
                (eval_date, eval_date),
            )
            row = cur.fetchone()
            if row is None or len(row) < 2 or row[0] is None or row[1] is None:
                raise ValueError("Breadth 200-DMA factor: no breadth data available - cannot calculate participation")

            above, total = int(row[0]), int(row[1])
            if total <= 0:
                raise ValueError(f"Breadth 200-DMA factor: No stocks available to calculate participation ({total} total)")
            pct = above / total * 100.0

            # Linear: 30% → 0, 55% → 50, 80% → 100
            score = max(0.0, min(100.0, (pct - 30) / 50 * 100))

            return {
                "score": score,
                "reason": f"Long-term breadth: {pct:.1f}% above 200-DMA",
                "details": {"pct_above": pct, "above": above, "total": total},
            }
        except Exception as e:
            logger.warning(f"Breadth 200-DMA calculation failed: {e}")
            raise ValueError(f"Breadth 200-DMA factor: {e}") from e
