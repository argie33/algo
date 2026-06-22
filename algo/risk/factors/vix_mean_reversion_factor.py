#!/usr/bin/env python3
"""VIX mean reversion factor strategy for market exposure calculation."""

import logging
from typing import Any

from algo.risk.market_factor_strategy import MarketFactorStrategy

logger = logging.getLogger(__name__)


class VixMeanReversionFactor(MarketFactorStrategy):
    """VIX mean reversion factor: deviation from short-term average.

    Detects extreme VIX readings that are likely to mean-revert quickly,
    providing timing for market recovery. Complements the VIX regime factor
    which measures general volatility environment.
    Weight: 4 points
    """

    @property
    def name(self) -> str:
        return "vix_mean_reversion"

    @property
    def weight(self) -> float:
        return 4.0  # 4 out of 100 total weight

    def calculate(self, eval_date: Any, cur: Any) -> dict[str, Any]:
        """Calculate VIX mean reversion potential (20-day moving average basis).

        When VIX is well above 20-day MA, it's likely to revert downward (bullish).
        When VIX is well below 20-day MA, it's likely to revert upward (bearish).

        Scoring based on deviation:
        - VIX > 1.3x 20-day MA = 100 (extreme fear, likely reversal up)
        - VIX > 1.1x 20-day MA = 70 (elevated fear, reversal likely)
        - VIX ~= 20-day MA = 50 (normal deviation)
        - VIX < 0.9x 20-day MA = 30 (low volatility, reversal up likely)
        - VIX < 0.7x 20-day MA = 0 (extreme complacency, reversal up needed)

        Raises ValueError if VIX data unavailable.
        """
        try:
            cur.execute(
                """
                SELECT
                    (SELECT close FROM price_daily WHERE symbol = '^VIX' AND date <= %s
                     ORDER BY date DESC LIMIT 1) as vix_current,
                    AVG(close) FILTER (
                        WHERE symbol = '^VIX' AND date > %s::date - INTERVAL '20 days' AND date <= %s
                    ) as vix_20d_ma
                FROM price_daily
                WHERE symbol = '^VIX' AND date <= %s
                LIMIT 1
                """,
                (eval_date, eval_date, eval_date, eval_date),
            )
            row = cur.fetchone()
            if not row or row[0] is None or row[1] is None:
                raise ValueError("VIX mean reversion factor: insufficient VIX data")

            vix_current = float(row[0])
            vix_20d_ma = float(row[1])

            if vix_20d_ma <= 0:
                raise ValueError("VIX mean reversion factor: invalid historical VIX")

            vix_ratio = vix_current / vix_20d_ma
            deviation_pct = (vix_current - vix_20d_ma) / vix_20d_ma * 100

            # Scoring based on mean reversion potential
            if vix_ratio > 1.3:
                score = 100.0
                signal = "extreme_fear_reversion"
            elif vix_ratio > 1.1:
                score = 70.0
                signal = "elevated_fear_reversion"
            elif vix_ratio >= 0.9:
                score = 50.0
                signal = "normal_deviation"
            elif vix_ratio >= 0.7:
                score = 30.0
                signal = "low_volatility"
            else:
                score = 0.0
                signal = "extreme_complacency"

            return {
                "score": score,
                "reason": f"VIX mean reversion: {vix_current:.2f} vs {vix_20d_ma:.2f} MA ({signal})",
                "details": {
                    "vix_current": vix_current,
                    "vix_20d_ma": vix_20d_ma,
                    "vix_ratio": vix_ratio,
                    "deviation_pct": deviation_pct,
                    "signal": signal,
                },
            }
        except Exception as e:
            logger.warning(f"VIX mean reversion calculation failed: {e}")
            raise ValueError(f"VIX mean reversion factor: {e}") from e
