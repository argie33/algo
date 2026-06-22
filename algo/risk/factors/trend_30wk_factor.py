#!/usr/bin/env python3
"""Trend 30-week factor strategy for market exposure calculation."""

import logging
from typing import Any

from algo.risk.market_factor_strategy import MarketFactorStrategy

logger = logging.getLogger(__name__)


class Trend30WkFactor(MarketFactorStrategy):
    """30-week trend factor.

    Tracks SPY price vs rising/flat/falling 30-week moving average.
    Weight: 15 points (strongest signal in composite)
    """

    @property
    def name(self) -> str:
        return "trend_30wk"

    @property
    def weight(self) -> float:
        return 15.0  # 15 out of 100 total weight

    def calculate(self, eval_date: Any, cur: Any) -> dict[str, Any]:
        """Calculate trend relative to 30-week MA.

        Raises ValueError if SPY price or 30-week MA data unavailable.

        Scoring:
        - SPY > 30-week MA by 5%+ = 100 (confirmed uptrend)
        - SPY > 30-week MA by 1-5% = 75 (uptrend forming)
        - SPY within 1% of 30-week MA = 50 (neutral/consolidation)
        - SPY < 30-week MA by 1-5% = 25 (downtrend forming)
        - SPY < 30-week MA by 5%+ = 0 (confirmed downtrend)
        """
        cur.execute("""
            SELECT close, date FROM price_daily
            WHERE symbol='SPY'
            ORDER BY date DESC
            LIMIT 1
        """)
        current_row = cur.fetchone()
        if not current_row or current_row[0] is None:
            raise ValueError("30-week trend factor: no current SPY price data - cannot calculate trend")

        current_price = float(current_row[0])

        # Calculate 30-week MA (approx 210 days)
        cur.execute("""
            SELECT AVG(close) FROM price_daily
            WHERE symbol='SPY'
              AND date >= DATE(CURRENT_DATE - INTERVAL '210 days')
              AND close IS NOT NULL
        """)
        ma_row = cur.fetchone()
        if not ma_row or ma_row[0] is None:
            raise ValueError("30-week trend factor: insufficient historical data for 30-week MA calculation")

        ma_30wk = float(ma_row[0])
        pct_above = ((current_price - ma_30wk) / ma_30wk) * 100

        # Scoring based on distance from 30-week MA
        if pct_above >= 5:
            return {
                "score": 100,
                "reason": f"Confirmed uptrend (SPY +{pct_above:.1f}% above 30-week MA)",
                "details": {
                    "price": current_price,
                    "ma_30wk": ma_30wk,
                    "pct_above": pct_above,
                },
            }
        elif pct_above >= 1:
            score = 75 + (pct_above - 1) / 4 * 25  # Scale 1-5% → 75-100
            return {
                "score": score,
                "reason": f"Uptrend forming (SPY +{pct_above:.1f}% above 30-week MA)",
                "details": {
                    "price": current_price,
                    "ma_30wk": ma_30wk,
                    "pct_above": pct_above,
                },
            }
        elif pct_above >= -1:
            return {
                "score": 50,
                "reason": f"Neutral/consolidation (SPY {pct_above:+.1f}% vs 30-week MA)",
                "details": {
                    "price": current_price,
                    "ma_30wk": ma_30wk,
                    "pct_above": pct_above,
                },
            }
        elif pct_above >= -5:
            score = 25 - (abs(pct_above) - 1) / 4 * 25  # Scale -5% to -1% → 25-0
            return {
                "score": score,
                "reason": f"Downtrend forming (SPY {pct_above:.1f}% below 30-week MA)",
                "details": {
                    "price": current_price,
                    "ma_30wk": ma_30wk,
                    "pct_above": pct_above,
                },
            }
        else:
            return {
                "score": 0,
                "reason": f"Confirmed downtrend (SPY {pct_above:.1f}% below 30-week MA)",
                "details": {
                    "price": current_price,
                    "ma_30wk": ma_30wk,
                    "pct_above": pct_above,
                },
            }
