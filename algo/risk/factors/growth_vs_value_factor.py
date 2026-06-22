#!/usr/bin/env python3
"""Growth vs value leadership factor strategy."""

import logging
from typing import Any

from algo.risk.market_factor_strategy import MarketFactorStrategy


logger = logging.getLogger(__name__)


class GrowthVsValueFactor(MarketFactorStrategy):
    """Market leadership style factor: Nasdaq-100 vs S&P 500 momentum ratio.

    When growth (Nasdaq-heavy) outperforms value (S&P 500), signals
    risk-on appetite and confidence in low-rate environment.
    When value outperforms, signals economic concerns and rate sensitivity.
    Weight: 5 points
    """

    @property
    def name(self) -> str:
        return "growth_vs_value"

    @property
    def weight(self) -> float:
        return 5.0  # 5 out of 100 total weight

    def calculate(self, eval_date: Any, cur: Any) -> dict[str, Any]:
        """Calculate growth/Nasdaq momentum vs value/SPY (20-day horizon).

        Uses QQQ (Nasdaq-100) vs SPY as proxy for growth vs value rotation.

        Scoring based on relative momentum:
        - QQQ +3%+ ahead of SPY = 100 (growth leadership)
        - QQQ +1% to +3% ahead = 70 (moderate growth)
        - Within 1% = 50 (balanced)
        - SPY +1% to +3% ahead = 30 (value leadership)
        - SPY +3%+ ahead = 0 (strong value outperformance)

        Raises ValueError if price data unavailable.
        """
        try:
            cur.execute(
                """
                SELECT
                    (SELECT close FROM price_daily WHERE symbol = 'QQQ' AND date <= %s
                     ORDER BY date DESC LIMIT 1) as qqq_current,
                    (SELECT close FROM price_daily WHERE symbol = 'QQQ' AND date <= %s
                     ORDER BY date DESC LIMIT 1 OFFSET 20) as qqq_20d_ago,
                    (SELECT close FROM price_daily WHERE symbol = 'SPY' AND date <= %s
                     ORDER BY date DESC LIMIT 1) as spy_current,
                    (SELECT close FROM price_daily WHERE symbol = 'SPY' AND date <= %s
                     ORDER BY date DESC LIMIT 1 OFFSET 20) as spy_20d_ago
                """,
                (eval_date, eval_date, eval_date, eval_date),
            )
            row = cur.fetchone()
            if not row or row[0] is None or row[2] is None:
                raise ValueError("Growth vs value factor: missing price data for QQQ or SPY")

            qqq_curr = float(row[0])
            qqq_20d = float(row[1]) if row[1] else qqq_curr
            spy_curr = float(row[2])
            spy_20d = float(row[3]) if row[3] else spy_curr

            if qqq_20d <= 0 or spy_20d <= 0:
                raise ValueError("Growth vs value factor: invalid historical prices")

            qqq_ret = (qqq_curr - qqq_20d) / qqq_20d * 100
            spy_ret = (spy_curr - spy_20d) / spy_20d * 100
            growth_outperformance = qqq_ret - spy_ret

            # Scoring based on growth vs value leadership
            if growth_outperformance >= 3.0:
                score = 100.0
                signal = "growth_leadership"
            elif growth_outperformance >= 1.0:
                score = 70.0
                signal = "moderate_growth"
            elif growth_outperformance >= -1.0:
                score = 50.0
                signal = "balanced"
            elif growth_outperformance >= -3.0:
                score = 30.0
                signal = "value_leadership"
            else:
                score = 0.0
                signal = "strong_value_outperformance"

            return {
                "score": score,
                "reason": f"Growth vs value: {growth_outperformance:+.2f}% ({signal})",
                "details": {
                    "qqq_ret_20d": qqq_ret,
                    "spy_ret_20d": spy_ret,
                    "growth_outperformance": growth_outperformance,
                    "signal": signal,
                },
            }
        except Exception as e:
            logger.warning(f"Growth vs value calculation failed: {e}")
            raise ValueError(f"Growth vs value factor: {e}") from e
