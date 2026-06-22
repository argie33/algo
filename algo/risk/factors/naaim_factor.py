#!/usr/bin/env python3
"""NAAIM (National Association of Active Investment Managers) factor strategy."""

import logging
from typing import Any

from algo.risk.market_factor_strategy import MarketFactorStrategy


logger = logging.getLogger(__name__)


class NAAIMFactor(MarketFactorStrategy):
    """Professional manager positioning factor: contrarian at extremes.

    NAAIM manager equity exposure (0-100% scale):
    - < 20: heavily underweight → contrarian bullish (managers forced to buy)
    - > 80: heavily overweight → contrarian cautious (limited buying power)
    Weight: 5 points
    """

    @property
    def name(self) -> str:
        return "naaim"

    @property
    def weight(self) -> float:
        return 5.0  # 5 out of 100 total weight

    def calculate(self, eval_date: Any, cur: Any) -> dict[str, Any]:
        """Calculate contrarian professional manager positioning from NAAIM.

        Scoring (contrarian):
        - < 20% exposure = 90 (maximum underweight fear → buy signal)
        - 20-35% exposure = 75 (elevated caution)
        - 35-55% exposure = 55 (neutral)
        - 55-70% exposure = 40 (elevated bullishness)
        - 70-85% exposure = 25 (elevated complacency)
        - > 85% exposure = 15 (maximum overweight greed → caution)

        Raises ValueError if NAAIM data unavailable.
        """
        try:
            cur.execute(
                """
                SELECT naaim_number_mean
                FROM naaim
                WHERE date <= %s
                ORDER BY date DESC LIMIT 1
                """,
                (eval_date,),
            )
            row = cur.fetchone()
            if not row or row[0] is None:
                raise ValueError("NAAIM factor: no manager positioning data available")

            exposure = float(row[0])
            clamped = max(0.0, min(100.0, exposure))

            # Contrarian scoring at extremes
            if clamped < 20:
                score = 90.0
                signal = "extreme_underweight"
            elif clamped < 35:
                score = 75.0
                signal = "elevated_caution"
            elif clamped < 55:
                score = 55.0
                signal = "neutral"
            elif clamped < 70:
                score = 40.0
                signal = "elevated_bullishness"
            elif clamped < 85:
                score = 25.0
                signal = "elevated_complacency"
            else:
                score = 15.0
                signal = "extreme_overweight"

            return {
                "score": score,
                "reason": f"NAAIM exposure: {clamped:.1f}% ({signal})",
                "details": {"exposure_pct": exposure, "signal": signal},
            }
        except Exception as e:
            logger.warning(f"NAAIM calculation failed: {e}")
            raise ValueError(f"NAAIM factor: {e}") from e
