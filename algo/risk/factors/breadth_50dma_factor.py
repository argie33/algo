#!/usr/bin/env python3
"""Breadth 50-day moving average factor strategy for market exposure calculation."""

import logging
from typing import Any

from psycopg2 import sql as pgsql

from algo.risk.market_factor_strategy import MarketFactorStrategy

logger = logging.getLogger(__name__)


class Breadth50DMAFactor(MarketFactorStrategy):
    """Short-term breadth factor: % stocks above 50-day MA.

    Measures market participation in the short-term uptrend (daily to weekly).
    Weight: 6 points
    """

    @property
    def name(self) -> str:
        return "breadth_50dma"

    @property
    def weight(self) -> float:
        return 6.0  # 6 out of 100 total weight

    def calculate(self, eval_date: Any, cur: Any) -> dict[str, Any]:
        """Calculate % of stocks trading above 50-day MA.

        Scoring (linear):
        - 80%+ above 50-DMA = 100 (strong participation)
        - 50% above 50-DMA = 50 (neutral)
        - 20% above 50-DMA = 0 (weak participation)
        - <20% above 50-DMA = 0 (bearish participation)

        Raises ValueError if breadth data unavailable.
        """
        col = pgsql.Identifier("price_above_sma50")
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
            if not row or not row[1]:
                raise ValueError("Breadth 50-DMA factor: no breadth data available - cannot calculate participation")

            above, total = int(row[0]), int(row[1])
            pct = above / total * 100.0 if total > 0 else 0

            # Linear: 20% → 0, 50% → 50, 80% → 100
            score = max(0.0, min(100.0, (pct - 20) / 60 * 100))

            return {
                "score": score,
                "reason": f"Short-term breadth: {pct:.1f}% above 50-DMA",
                "details": {"pct_above": pct, "above": above, "total": total},
            }
        except Exception as e:
            logger.warning(f"Breadth 50-DMA calculation failed: {e}")
            raise ValueError(f"Breadth 50-DMA factor: {e}") from e
