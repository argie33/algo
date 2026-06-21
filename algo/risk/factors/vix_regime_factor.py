#!/usr/bin/env python3
"""VIX regime factor strategy for market exposure calculation."""

import logging
from typing import Any

from algo.risk.market_factor_strategy import MarketFactorStrategy


logger = logging.getLogger(__name__)


class VixRegimeFactor(MarketFactorStrategy):
    """VIX regime factor.

    Scores based on VIX level and term structure (VIX3M/VIX ratio).
    Weight: 10 points
    """

    @property
    def name(self) -> str:
        return "vix"

    @property
    def weight(self) -> float:
        return 10.0  # 10 out of 100 total weight

    def calculate(self, eval_date: Any, cur: Any) -> dict[str, Any]:
        """Calculate VIX regime and term structure score.

        Regime scoring:
        - VIX < 15: complacency, score ~65
        - VIX 15-25: normal, score ~75-80
        - VIX 25-35: elevated, score ~50-60
        - VIX > 35: crisis, score ~20-30

        Term structure (VIX3M/VIX):
        - Contango (>1.0): futures rising, backwardation easing, score boost
        - Backwardation (<1.0): near-term stress, score penalty
        """
        try:
            cur.execute("""
                SELECT vix_level, vix_3m_level
                FROM market_health_daily
                ORDER BY date DESC
                LIMIT 1
            """)
            row = cur.fetchone()
            if not row:
                return {"score": 75, "reason": "No VIX data available", "error": "missing_data"}

            vix_level, vix_3m = row[0], row[1]
            if vix_level is None:
                return {"score": 75, "reason": "VIX level is NULL", "error": "null_data"}

            vix_level = float(vix_level)

            # Base score from VIX level
            if vix_level < 15:
                base_score = 65.0  # Complacency
            elif vix_level < 25:
                # Linear interpolation: 15-25 → 75-80
                base_score = 75 + (vix_level - 15) / 10 * 5
            elif vix_level < 35:
                # Linear interpolation: 25-35 → 60-50
                base_score = 60 - (vix_level - 25) / 10 * 10
            else:
                base_score = 20 + min(10, (35 - vix_level) / -5)  # Cap at ~20 for extreme VIX

            # Adjust for term structure if available
            adjustment = 0.0
            if vix_3m is not None:
                vix_3m = float(vix_3m)
                term_ratio = vix_3m / vix_level if vix_level > 0 else 1.0

                if term_ratio > 1.05:
                    # Contango: futures rising, boost score (forward-looking optimism)
                    adjustment = min(10, (term_ratio - 1.0) * 20)
                elif term_ratio < 0.95:
                    # Backwardation: near-term stress, penalize score
                    adjustment = max(-10, (term_ratio - 1.0) * 20)

            final_score = max(0, min(100, base_score + adjustment))

            return {
                "score": final_score,
                "reason": f"VIX {vix_level:.1f}" + (f", term {term_ratio:.2f} ({adjustment:+.0f})" if vix_3m else ""),
                "details": {
                    "vix": vix_level,
                    "vix_3m": vix_3m,
                    "base_score": base_score,
                    "adjustment": adjustment,
                },
            }

        except Exception as e:
            logger.error(f"Failed to calculate VIX regime factor: {e}")
            return {"score": 75, "reason": f"Calculation error: {e}", "error": str(e)}
