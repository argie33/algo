#!/usr/bin/env python3
"""Russell 2000 vs S&P 500 leadership factor strategy."""

import logging
from typing import Any

from algo.risk.market_factor_strategy import MarketFactorStrategy


logger = logging.getLogger(__name__)


class RussellVsSpyFactor(MarketFactorStrategy):
    """Small-cap leadership factor: Russell 2000 vs S&P 500 momentum ratio.

    When small-caps outperform large-caps, signals risk-on appetite and
    economic optimism. When small-caps underperform, signals risk-off and
    preference for mega-cap safety.
    Weight: 5 points
    """

    @property
    def name(self) -> str:
        return "russell_vs_spy"

    @property
    def weight(self) -> float:
        return 5.0  # 5 out of 100 total weight

    def calculate(self, eval_date: Any, cur: Any) -> dict[str, Any]:
        """Calculate Russell 2000 outperformance vs S&P 500 (20-day horizon).

        Scoring based on relative momentum:
        - Russell +2%+ ahead of SPY = 100 (risk-on strength)
        - Russell +0.5% to +2% ahead = 70 (moderate risk-on)
        - Within 0.5% = 50 (neutral positioning)
        - SPY +0.5% to +2% ahead = 30 (mild risk-off)
        - SPY +2%+ ahead = 0 (strong risk-off)

        Raises ValueError if price data unavailable.
        """
        try:
            cur.execute(
                """
                SELECT
                    (SELECT close FROM price_daily WHERE symbol = 'IWM' AND date <= %s
                     ORDER BY date DESC LIMIT 1) as rrr_current,
                    (SELECT close FROM price_daily WHERE symbol = 'IWM' AND date <= %s
                     ORDER BY date DESC LIMIT 1 OFFSET 20) as rrr_20d_ago,
                    (SELECT close FROM price_daily WHERE symbol = 'SPY' AND date <= %s
                     ORDER BY date DESC LIMIT 1) as spy_current,
                    (SELECT close FROM price_daily WHERE symbol = 'SPY' AND date <= %s
                     ORDER BY date DESC LIMIT 1 OFFSET 20) as spy_20d_ago
                """,
                (eval_date, eval_date, eval_date, eval_date),
            )
            row = cur.fetchone()
            if not row or row[0] is None or row[2] is None:
                raise ValueError("Russell vs SPY factor: missing price data for IWM or SPY")

            rrr_curr = float(row[0])
            rrr_20d = float(row[1]) if row[1] else rrr_curr
            spy_curr = float(row[2])
            spy_20d = float(row[3]) if row[3] else spy_curr

            if rrr_20d <= 0 or spy_20d <= 0:
                raise ValueError("Russell vs SPY factor: invalid historical prices")

            rrr_ret = (rrr_curr - rrr_20d) / rrr_20d * 100
            spy_ret = (spy_curr - spy_20d) / spy_20d * 100
            outperformance = rrr_ret - spy_ret

            # Scoring based on relative momentum
            if outperformance >= 2.0:
                score = 100.0
                signal = "strong_risk_on"
            elif outperformance >= 0.5:
                score = 70.0
                signal = "moderate_risk_on"
            elif outperformance >= -0.5:
                score = 50.0
                signal = "neutral"
            elif outperformance >= -2.0:
                score = 30.0
                signal = "mild_risk_off"
            else:
                score = 0.0
                signal = "strong_risk_off"

            return {
                "score": score,
                "reason": f"Russell vs SPY: {outperformance:+.2f}% ({signal})",
                "details": {
                    "russell_ret_20d": rrr_ret,
                    "spy_ret_20d": spy_ret,
                    "outperformance": outperformance,
                    "signal": signal,
                },
            }
        except Exception as e:
            logger.warning(f"Russell vs SPY calculation failed: {e}")
            raise ValueError(f"Russell vs SPY factor: {e}") from e
