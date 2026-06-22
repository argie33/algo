#!/usr/bin/env python3
"""Short-term momentum factor strategy for market exposure calculation."""

import logging
from typing import Any

from algo.risk.market_factor_strategy import MarketFactorStrategy


logger = logging.getLogger(__name__)


class ShortTermMomentumFactor(MarketFactorStrategy):
    """2-week price momentum factor.

    Captures short-term trend strength and continuation (daily to weekly horizon).
    Complements the 12-month momentum factor which measures longer-term direction.
    Weight: 6 points
    """

    @property
    def name(self) -> str:
        return "short_term_momentum"

    @property
    def weight(self) -> float:
        return 6.0  # 6 out of 100 total weight

    def calculate(self, eval_date: Any, cur: Any) -> dict[str, Any]:
        """Calculate 2-week (10 trading day) SPY momentum.

        Scoring based on return:
        - +5%+ = 100 (strong uptrend)
        - +2% to +5% = 70 (moderate uptrend)
        - -2% to +2% = 50 (consolidation)
        - -2% to -5% = 30 (mild downtrend)
        - -5%+ = 0 (strong downtrend)

        Raises ValueError if price data unavailable.
        """
        try:
            cur.execute(
                """
                SELECT close FROM price_daily
                WHERE symbol = 'SPY' AND date <= %s
                ORDER BY date DESC LIMIT 12
                """,
                (eval_date,),
            )
            rows = cur.fetchall()
            if len(rows) < 11:
                raise ValueError("Short-term momentum factor: insufficient history (need 10+ trading days)")

            current_close = float(rows[0][0])
            past_close = float(rows[10][0])  # 10 trading days ago

            if past_close <= 0:
                raise ValueError("Short-term momentum factor: invalid historical price")

            momentum_pct = (current_close - past_close) / past_close * 100

            # Short-term momentum scoring
            if momentum_pct >= 5:
                score = 100.0
                signal = "strong_uptrend"
            elif momentum_pct >= 2:
                score = 70.0
                signal = "moderate_uptrend"
            elif momentum_pct >= -2:
                score = 50.0
                signal = "consolidation"
            elif momentum_pct >= -5:
                score = 30.0
                signal = "mild_downtrend"
            else:
                score = 0.0
                signal = "strong_downtrend"

            return {
                "score": score,
                "reason": f"Short-term momentum: {momentum_pct:+.2f}% ({signal})",
                "details": {
                    "momentum_pct": momentum_pct,
                    "current_price": current_close,
                    "price_10d_ago": past_close,
                    "signal": signal,
                },
            }
        except Exception as e:
            logger.warning(f"Short-term momentum calculation failed: {e}")
            raise ValueError(f"Short-term momentum factor: {e}") from e
