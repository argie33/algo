#!/usr/bin/env python3
"""New highs vs new lows factor strategy for market exposure calculation."""

import logging
from typing import Any

from algo.risk.market_factor_strategy import MarketFactorStrategy

logger = logging.getLogger(__name__)


class NewHighsLowsFactor(MarketFactorStrategy):
    """Market leadership quality factor: 52-week new highs vs new lows.

    Measures the breadth and quality of market leadership.
    Weight: 7 points
    """

    @property
    def name(self) -> str:
        return "new_highs_lows"

    @property
    def weight(self) -> float:
        return 7.0  # 7 out of 100 total weight

    def calculate(self, eval_date: Any, cur: Any) -> dict[str, Any]:
        """Calculate market leadership from new 52-week highs vs lows ratio.

        Scoring based on high% (new_highs / (new_highs + new_lows)):
        - > 80% = 100 (strong leadership, broad rally)
        - 50-80% = 70 (mixed leadership)
        - 20-50% = 30 (weak leadership, few new highs)
        - < 20% = 0 (poor leadership, concentrated decline)

        Raises ValueError if breadth data unavailable.
        """
        try:
            cur.execute(
                """
                SELECT new_highs_count, new_lows_count
                FROM market_health_daily
                WHERE date <= %s AND new_highs_count IS NOT NULL
                ORDER BY date DESC LIMIT 1
                """,
                (eval_date,),
            )
            row = cur.fetchone()
            if not row:
                raise ValueError("New highs/lows factor: no breadth data available")

            nh = int(row[0] or 0)
            nl = int(row[1] or 0)
            total = nh + nl

            if total == 0:
                raise ValueError("New highs/lows factor: no new highs or new lows data")

            nh_pct = nh * 100.0 / total
            net = nh - nl

            # Scoring based on NH%
            if nh_pct > 80:
                score = 100.0
                signal = "strong_leadership"
            elif nh_pct > 50:
                score = 70.0
                signal = "mixed_leadership"
            elif nh_pct > 20:
                score = 30.0
                signal = "weak_leadership"
            else:
                score = 0.0
                signal = "poor_leadership"

            return {
                "score": score,
                "reason": f"Market leadership: {nh_pct:.1f}% new highs ({signal})",
                "details": {
                    "new_highs": nh,
                    "new_lows": nl,
                    "nh_pct": nh_pct,
                    "net": net,
                    "signal": signal,
                },
            }
        except Exception as e:
            logger.warning(f"New highs/lows calculation failed: {e}")
            raise ValueError(f"New highs/lows factor: {e}") from e
