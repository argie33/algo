#!/usr/bin/env python3
"""Inflation risk factor strategy: oil price relative strength indicator."""

import logging
from typing import Any

from algo.risk.market_factor_strategy import MarketFactorStrategy

logger = logging.getLogger(__name__)


class InflationRiskFactor(MarketFactorStrategy):
    """Inflation/commodity risk factor: oil price momentum vs S&P 500.

    When oil rallies while SPY is declining, signals inflation concerns (bearish).
    When oil declines while SPY is rising, signals disinflationary environment (bullish).
    Weight: 4 points
    """

    @property
    def name(self) -> str:
        return "inflation_risk"

    @property
    def weight(self) -> float:
        return 4.0  # 4 out of 100 total weight

    def calculate(self, eval_date: Any, cur: Any) -> dict[str, Any]:
        """Calculate inflation risk from oil/SPY relative momentum (20-day).

        Scoring based on relative momentum:
        - SPY +2%+ while Oil ≤0% = 100 (disinflationary bull)
        - SPY +1% while Oil ≤+0.5% = 70 (moderate disinflationary)
        - SPY and Oil roughly equal moves = 50 (neutral inflation backdrop)
        - Oil +1% while SPY ≤+0.5% = 30 (inflation building)
        - Oil +2%+ while SPY ≤0% = 0 (stagflationary risk)

        Raises ValueError if price data unavailable.
        """
        try:
            cur.execute(
                """
                SELECT
                    (SELECT close FROM price_daily WHERE symbol = 'SPY' AND date <= %s
                     ORDER BY date DESC LIMIT 1) as spy_current,
                    (SELECT close FROM price_daily WHERE symbol = 'SPY' AND date <= %s
                     ORDER BY date DESC LIMIT 1 OFFSET 20) as spy_20d_ago,
                    (SELECT close FROM price_daily WHERE symbol = 'USO' AND date <= %s
                     ORDER BY date DESC LIMIT 1) as oil_current,
                    (SELECT close FROM price_daily WHERE symbol = 'USO' AND date <= %s
                     ORDER BY date DESC LIMIT 1 OFFSET 20) as oil_20d_ago
                """,
                (eval_date, eval_date, eval_date, eval_date),
            )
            row = cur.fetchone()
            if not row or row[0] is None or row[2] is None:
                raise ValueError("Inflation risk factor: missing price data for SPY or USO")

            spy_curr = float(row[0])
            if row[1] is None:
                raise ValueError(
                    "Inflation risk factor: historical SPY price (20 days ago) unavailable. "
                    "Cannot calculate inflation risk momentum without complete price history."
                )
            spy_20d = float(row[1])
            oil_curr = float(row[2])
            if row[3] is None:
                raise ValueError(
                    "Inflation risk factor: historical oil price (20 days ago) unavailable. "
                    "Cannot calculate inflation risk momentum without complete price history."
                )
            oil_20d = float(row[3])

            if spy_20d <= 0 or oil_20d <= 0:
                raise ValueError("Inflation risk factor: invalid historical prices")

            spy_ret = (spy_curr - spy_20d) / spy_20d * 100
            oil_ret = (oil_curr - oil_20d) / oil_20d * 100
            inflation_spread = oil_ret - spy_ret

            # Scoring based on inflation risk signal
            # Negative spread = disinflationary (bullish for equities)
            # Positive spread = inflationary risk (bearish for equities)
            if inflation_spread <= -2.0:
                score = 100.0
                signal = "disinflationary_bull"
            elif inflation_spread <= -0.5:
                score = 70.0
                signal = "moderate_disinflationary"
            elif inflation_spread <= 0.5:
                score = 50.0
                signal = "neutral_inflation"
            elif inflation_spread <= 2.0:
                score = 30.0
                signal = "inflation_building"
            else:
                score = 0.0
                signal = "stagflationary_risk"

            return {
                "score": score,
                "reason": f"Inflation risk: {inflation_spread:+.2f}% oil-SPY spread ({signal})",
                "details": {
                    "spy_ret_20d": spy_ret,
                    "oil_ret_20d": oil_ret,
                    "inflation_spread": inflation_spread,
                    "signal": signal,
                },
            }
        except Exception as e:
            logger.warning(f"Inflation risk calculation failed: {e}")
            raise ValueError(f"Inflation risk factor: {e}") from e
