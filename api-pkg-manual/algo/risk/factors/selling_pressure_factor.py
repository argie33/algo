#!/usr/bin/env python3
"""Selling pressure (distribution days) factor strategy for market exposure calculation."""

import logging
from typing import Any

from algo.risk.market_factor_strategy import MarketFactorStrategy

logger = logging.getLogger(__name__)


class SellingPressureFactor(MarketFactorStrategy):
    """Institutional selling pressure factor: heavy-volume down days.

    Counts days with market close down ≥0.2% on above-average volume,
    indicating institutional distribution rather than retail selling.
    Weight: 10 points
    """

    @property
    def name(self) -> str:
        return "distribution_days"

    @property
    def weight(self) -> float:
        return 10.0  # 10 out of 100 total weight

    def calculate(self, eval_date: Any, cur: Any) -> dict[str, Any]:
        """Calculate selling pressure from heavy-volume down days.

        Counts sessions over last 25 trading days where SPY closes down ≥0.2%
        on above-average volume (sign of institutional distribution).

        Scoring (gradient):
        - 0-2 days = 100 (clean absorption)
        - 3-4 days = 60 (caution building)
        - 5+ days = 20 (pressure mounting)
        - 6+ days also triggers hard veto cap

        Raises ValueError if price/volume data unavailable.
        """
        try:
            cur.execute(
                """
                WITH d AS (
                    SELECT close, volume,
                           LAG(close) OVER (ORDER BY date) AS prev_close,
                           AVG(volume) OVER (ORDER BY date ROWS BETWEEN 49 PRECEDING AND 1 PRECEDING) as avg50
                    FROM price_daily
                    WHERE symbol = 'SPY' AND date <= %s
                    ORDER BY date DESC LIMIT 26
                )
                SELECT COUNT(*) FILTER (WHERE close < prev_close * 0.998 AND volume > avg50) FROM d
                WHERE prev_close IS NOT NULL
                """,
                (eval_date,),
            )
            row = cur.fetchone()
            if not row:
                raise ValueError("Selling pressure factor: could not query price/volume data")

            if row[0] is None:
                raise ValueError(
                    "Selling pressure factor: distribution day count is NULL. "
                    "Cannot calculate institutional selling pressure without valid price/volume data."
                )
            count = int(row[0])

            # Gradient scoring: lower = more distribution
            if count <= 2:
                score = 100.0
                regime = "clean"
            elif count <= 4:
                score = 60.0
                regime = "caution"
            else:  # 5+
                score = 20.0
                regime = "pressure"

            return {
                "score": score,
                "reason": f"Selling pressure: {count} heavy-volume down days ({regime})",
                "details": {"distribution_days": count, "regime": regime},
            }
        except Exception as e:
            logger.warning(f"Selling pressure calculation failed: {e}")
            raise ValueError(f"Selling pressure factor: {e}") from e
