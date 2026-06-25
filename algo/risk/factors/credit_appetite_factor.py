#!/usr/bin/env python3
"""Credit appetite factor strategy: high-yield vs investment-grade bond momentum."""

import logging
from typing import Any

from algo.risk.market_factor_strategy import MarketFactorStrategy

logger = logging.getLogger(__name__)


class CreditAppetiteFactor(MarketFactorStrategy):
    """Risk appetite indicator: HYG (high-yield bonds) vs LQD (investment-grade).

    When investors accept higher credit risk (HYG outperforms LQD),
    signals elevated risk appetite and confidence in economic growth.
    When they flee to safety (LQD outperforms), signals risk aversion.
    Weight: 5 points
    """

    @property
    def name(self) -> str:
        return "credit_appetite"

    @property
    def weight(self) -> float:
        return 5.0  # 5 out of 100 total weight

    def calculate(self, eval_date: Any, cur: Any) -> dict[str, Any]:
        """Calculate credit risk appetite from HYG/LQD ratio (20-day momentum).

        Scoring based on relative momentum:
        - HYG +1.5%+ ahead of LQD = 100 (strong risk appetite)
        - HYG +0.5% to +1.5% ahead = 70 (elevated appetite)
        - Within 0.5% = 50 (neutral)
        - LQD +0.5% to +1.5% ahead = 30 (elevated caution)
        - LQD +1.5%+ ahead = 0 (strong flight-to-quality)

        Raises ValueError if bond price data unavailable.
        """
        try:
            cur.execute(
                """
                SELECT
                    (SELECT close FROM price_daily WHERE symbol = 'HYG' AND date <= %s
                     ORDER BY date DESC LIMIT 1) as hyg_current,
                    (SELECT close FROM price_daily WHERE symbol = 'HYG' AND date <= %s
                     ORDER BY date DESC LIMIT 1 OFFSET 20) as hyg_20d_ago,
                    (SELECT close FROM price_daily WHERE symbol = 'LQD' AND date <= %s
                     ORDER BY date DESC LIMIT 1) as lqd_current,
                    (SELECT close FROM price_daily WHERE symbol = 'LQD' AND date <= %s
                     ORDER BY date DESC LIMIT 1 OFFSET 20) as lqd_20d_ago
                """,
                (eval_date, eval_date, eval_date, eval_date),
            )
            row = cur.fetchone()
            if not row or row[0] is None or row[2] is None:
                raise ValueError("Credit appetite factor: missing price data for HYG or LQD")

            hyg_curr = float(row[0])
            if row[1] is None:
                raise ValueError(
                    "Credit appetite factor: historical HYG price (20 days ago) unavailable. "
                    "Cannot calculate credit risk appetite momentum without complete price history."
                )
            hyg_20d = float(row[1])
            lqd_curr = float(row[2])
            if row[3] is None:
                raise ValueError(
                    "Credit appetite factor: historical LQD price (20 days ago) unavailable. "
                    "Cannot calculate credit risk appetite momentum without complete price history."
                )
            lqd_20d = float(row[3])

            if hyg_20d <= 0 or lqd_20d <= 0:
                raise ValueError("Credit appetite factor: invalid historical prices")

            hyg_ret = (hyg_curr - hyg_20d) / hyg_20d * 100
            lqd_ret = (lqd_curr - lqd_20d) / lqd_20d * 100
            risk_appetite_diff = hyg_ret - lqd_ret

            # Scoring based on credit risk appetite
            if risk_appetite_diff >= 1.5:
                score = 100.0
                signal = "strong_risk_appetite"
            elif risk_appetite_diff >= 0.5:
                score = 70.0
                signal = "elevated_appetite"
            elif risk_appetite_diff >= -0.5:
                score = 50.0
                signal = "neutral_appetite"
            elif risk_appetite_diff >= -1.5:
                score = 30.0
                signal = "elevated_caution"
            else:
                score = 0.0
                signal = "flight_to_quality"

            return {
                "score": score,
                "reason": f"Credit appetite: {risk_appetite_diff:+.2f}% ({signal})",
                "details": {
                    "hyg_ret_20d": hyg_ret,
                    "lqd_ret_20d": lqd_ret,
                    "risk_appetite_diff": risk_appetite_diff,
                    "signal": signal,
                },
            }
        except Exception as e:
            logger.warning(f"Credit appetite calculation failed: {e}")
            raise ValueError(f"Credit appetite factor: {e}") from e
