#!/usr/bin/env python3
"""Yield curve steepness factor strategy for market exposure calculation."""

import logging
from typing import Any

from algo.risk.market_factor_strategy import MarketFactorStrategy


logger = logging.getLogger(__name__)


class YieldCurveFactor(MarketFactorStrategy):
    """Yield curve steepness factor: 10Y-2Y spread as economic growth signal.

    Steep curve (positive spread): economic growth and inflation expectations
    (equity-friendly environment).
    Flat/inverted curve: economic slowdown and recession risk (equity-cautious).
    Weight: 5 points
    """

    @property
    def name(self) -> str:
        return "yield_curve"

    @property
    def weight(self) -> float:
        return 5.0  # 5 out of 100 total weight

    def calculate(self, eval_date: Any, cur: Any) -> dict[str, Any]:
        """Calculate yield curve slope and economic growth signal.

        Uses T10Y2Y (10-year minus 2-year Treasury spread).

        Scoring based on spread:
        - > 2.0% = 100 (steep curve, strong growth)
        - 1.0% to 2.0% = 70 (moderate curve, normal growth)
        - 0% to 1.0% = 40 (flattening, growth slowdown)
        - -0.5% to 0% = 20 (inverted, recession risk)
        - < -0.5% = 0 (deeply inverted, high recession risk)

        Raises ValueError if yield curve data unavailable.
        """
        try:
            cur.execute(
                """
                SELECT value::float, date
                FROM economic_data
                WHERE series_id = 'T10Y2Y' AND date <= %s
                ORDER BY date DESC LIMIT 60
                """,
                (eval_date,),
            )
            rows = cur.fetchall()
            if not rows:
                raise ValueError("Yield curve factor: no T10Y2Y data available")

            current_spread = float(rows[0][0])
            # Check if spread has been inverted (history of inversion)
            weeks_inverted = sum(1 for r in rows[:12] if float(r[0]) < 0)

            # Scoring based on curve steepness
            if current_spread > 2.0:
                score = 100.0
                signal = "steep_growth"
            elif current_spread > 1.0:
                score = 70.0
                signal = "moderate_growth"
            elif current_spread > 0.0:
                score = 40.0
                signal = "flattening"
            elif current_spread > -0.5:
                score = 20.0
                signal = "inverted_caution"
            else:
                score = 0.0
                signal = "deeply_inverted"

            # Additional penalty if curve has been inverted for extended period
            inversion_penalty = 0
            if weeks_inverted >= 8:
                inversion_penalty = 15.0
                score = max(0.0, score - inversion_penalty)

            return {
                "score": score,
                "reason": f"Yield curve: {current_spread:.2f}% spread ({signal})" + (
                    f" - inverted {weeks_inverted}+ weeks" if weeks_inverted >= 8 else ""
                ),
                "details": {
                    "t10y2y_spread": current_spread,
                    "weeks_inverted": weeks_inverted,
                    "inversion_penalty": inversion_penalty,
                    "signal": signal,
                },
            }
        except Exception as e:
            logger.warning(f"Yield curve calculation failed: {e}")
            raise ValueError(f"Yield curve factor: {e}") from e
