#!/usr/bin/env python3
"""Credit spread factor strategy for market exposure calculation."""

import logging
from typing import Any

from algo.risk.market_factor_strategy import MarketFactorStrategy


logger = logging.getLogger(__name__)


class CreditSpreadFactor(MarketFactorStrategy):
    """HY credit spread factor: high-yield OAS leading indicator for equity stress.

    Credit spreads widen 4-6 weeks before equity markets price in credit risk.
    Based on Apollo/Torsten Slok research: credit leads equity.
    Weight: 10 points
    """

    @property
    def name(self) -> str:
        return "credit_spread"

    @property
    def weight(self) -> float:
        return 10.0  # 10 out of 100 total weight

    def calculate(self, eval_date: Any, cur: Any) -> dict[str, Any]:
        """Calculate credit stress from HY OAS (BAMLH0A0HYM2).

        Scoring based on spread level:
        - < 3.5% = 100 (tight/healthy)
        - 3.5-4.5% = 85 (mild stress forming)
        - 4.5-5.5% = 65 (moderate stress)
        - 5.5-7.0% = 35 (elevated stress)
        - > 7.0% = 10 (severe systemic stress)

        Also checks for rapid widening (>1pp in 20 days) as acceleration signal.

        Raises ValueError if credit data unavailable.
        """
        try:
            cur.execute(
                """
                SELECT value::float, date
                FROM economic_data
                WHERE series_id = 'BAMLH0A0HYM2' AND date <= %s
                ORDER BY date DESC LIMIT 25
                """,
                (eval_date,),
            )
            rows = cur.fetchall()
            if not rows:
                raise ValueError("Credit spread factor: no HY OAS data available")

            hy = float(rows[0][0])
            hy_20d_ago = float(rows[-1][0]) if len(rows) >= 20 else hy
            widening_1pp = (hy - hy_20d_ago) > 1.0

            # Base scoring on HY OAS level
            if hy < 3.5:
                score = 100.0
                regime = "healthy"
            elif hy < 4.5:
                score = 85.0
                regime = "mild_stress"
            elif hy < 5.5:
                score = 65.0
                regime = "moderate_stress"
            elif hy < 7.0:
                score = 35.0
                regime = "elevated_stress"
            else:
                score = 10.0
                regime = "severe_stress"

            # Rapid widening penalty: stress accelerating
            widening_penalty: float = 0
            if widening_1pp and hy > 4.0:
                widening_penalty = 20.0  # Additional penalty
                score = max(0.0, score - widening_penalty)

            return {
                "score": score,
                "reason": f"Credit spreads: HY OAS {hy:.2f}% ({regime})"
                + (", widening rapidly" if widening_1pp else ""),
                "details": {
                    "hy_oas": hy,
                    "hy_20d_ago": hy_20d_ago,
                    "widening_rapidly": widening_1pp,
                    "regime": regime,
                    "widening_penalty": widening_penalty,
                },
            }
        except Exception as e:
            logger.warning(f"Credit spread calculation failed: {e}")
            raise ValueError(f"Credit spread factor: {e}") from e
