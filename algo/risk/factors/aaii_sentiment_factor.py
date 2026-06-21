#!/usr/bin/env python3
"""AAII sentiment factor strategy for market exposure calculation."""

import logging
from typing import Any

from algo.risk.market_factor_strategy import MarketFactorStrategy


logger = logging.getLogger(__name__)


class AAIISentimentFactor(MarketFactorStrategy):
    """AAII Sentiment Index factor.

    Uses contrarian signal at extremes (±15+ spread between bullish/bearish).
    Neutral in middle range. Only scores at extremes; returns 50 (neutral) otherwise.

    Weight: 3 points (identifies dangerous extremes)
    """

    @property
    def name(self) -> str:
        return "aaii"

    @property
    def weight(self) -> float:
        return 3.0  # 3 out of 100 total weight

    def calculate(self, eval_date: Any, cur: Any) -> dict[str, Any]:
        """Calculate AAII sentiment factor.

        Returns score based on AAII bullish-bearish spread.
        Contrarian: high bearish spread (many bears) = bullish signal.
        """
        try:
            cur.execute("""
                SELECT bullish_pct, bearish_pct, date
                FROM aaii_sentiment_daily
                ORDER BY date DESC
                LIMIT 1
            """)
            row = cur.fetchone()
            if not row:
                return {"score": 50, "reason": "No AAII data available", "error": "missing_data"}

            bullish_pct, bearish_pct, date = row
            if bullish_pct is None or bearish_pct is None:
                return {"score": 50, "reason": "AAII percentages are NULL", "error": "null_data"}

            bullish_pct = float(bullish_pct)
            bearish_pct = float(bearish_pct)
            spread = bullish_pct - bearish_pct

            # Contrarian scoring: look for extremes
            # Extremely bearish (spread < -15) = bullish signal
            if spread < -15:
                score = 75 + min(10, abs(spread + 15) / 5)
                return {
                    "score": min(100, score),
                    "reason": f"Extreme bearish (spread={spread:.1f}) - contrarian bullish",
                    "details": {"bullish": bullish_pct, "bearish": bearish_pct, "spread": spread},
                }
            # Extremely bullish (spread > 15) = bearish signal
            elif spread > 15:
                score = 25 - min(10, (spread - 15) / 5)
                return {
                    "score": max(0, score),
                    "reason": f"Extreme bullish (spread={spread:.1f}) - contrarian bearish",
                    "details": {"bullish": bullish_pct, "bearish": bearish_pct, "spread": spread},
                }
            # Neutral range: -15 ≤ spread ≤ 15
            else:
                return {
                    "score": 50,
                    "reason": f"Neutral range (spread={spread:.1f})",
                    "details": {"bullish": bullish_pct, "bearish": bearish_pct, "spread": spread},
                }

        except Exception as e:
            logger.error(f"Failed to calculate AAII sentiment factor: {e}")
            return {"score": 50, "reason": f"Calculation error: {e}", "error": str(e)}
