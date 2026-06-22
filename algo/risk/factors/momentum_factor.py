#!/usr/bin/env python3
"""SPY momentum factor strategy for market exposure calculation."""

import logging
from typing import Any

from algo.risk.market_factor_strategy import MarketFactorStrategy


logger = logging.getLogger(__name__)


class MomentumFactor(MarketFactorStrategy):
    """SPY 12-month momentum factor (TSMOM).

    Most replicated quant signal per academic research (AQR, Moskowitz-Ooi-Pedersen).
    Weight: 10 points
    """

    @property
    def name(self) -> str:
        return "momentum"

    @property
    def weight(self) -> float:
        return 10.0  # 10 out of 100 total weight

    def calculate(self, eval_date: Any, cur: Any) -> dict[str, Any]:
        """Calculate 12-month trailing return momentum.

        Raises ValueError if SPY price data is unavailable.

        Scoring:
        - +25%+ return = 100 (strong uptrend momentum)
        - +10% to +25% = 75-90 (moderate momentum)
        - -5% to +10% = 40-75 (weak/neutral)
        - -10% to -5% = 20-40 (weak downtrend)
        - -25% to -10% = 10-20 (strong downtrend)
        - -25%+ = 0 (severe downtrend)
        """
        cur.execute("""
            SELECT close, date FROM price_daily
            WHERE symbol='SPY'
            ORDER BY date DESC
            LIMIT 1
        """)
        current_row = cur.fetchone()
        if not current_row or current_row[0] is None:
            raise ValueError("SPY momentum factor: no current price data in price_daily - cannot calculate momentum")

        current_price = float(current_row[0])

        # Get price from 12 months ago
        cur.execute("""
            SELECT close FROM price_daily
            WHERE symbol='SPY'
              AND date >= DATE(CURRENT_DATE - INTERVAL '365 days')
              AND date <= DATE(CURRENT_DATE - INTERVAL '365 days')
            ORDER BY date DESC
            LIMIT 1
        """)
        year_ago_row = cur.fetchone()

        if not year_ago_row or year_ago_row[0] is None:
            raise ValueError(
                "SPY momentum factor: insufficient historical data (12-month lookback) - cannot calculate momentum"
            )

        price_12m_ago = float(year_ago_row[0])
        return_pct = ((current_price - price_12m_ago) / price_12m_ago) * 100

        # Gradient scoring based on 12-month return
        if return_pct >= 25:
            return {
                "score": 100,
                "reason": f"Strong uptrend momentum (+{return_pct:.1f}% 12M return)",
                "details": {"current": current_price, "12m_ago": price_12m_ago, "return_pct": return_pct},
            }
        elif return_pct >= 10:
            # Scale 10-25% → 75-100
            score = 75 + (return_pct - 10) / 15 * 25
            return {
                "score": score,
                "reason": f"Moderate momentum (+{return_pct:.1f}% 12M return)",
                "details": {"current": current_price, "12m_ago": price_12m_ago, "return_pct": return_pct},
            }
        elif return_pct >= -5:
            # Scale -5% to +10% → 40-75
            score = 40 + (return_pct + 5) / 15 * 35
            return {
                "score": score,
                "reason": f"Weak/neutral ({return_pct:+.1f}% 12M return)",
                "details": {"current": current_price, "12m_ago": price_12m_ago, "return_pct": return_pct},
            }
        elif return_pct >= -10:
            # Scale -10% to -5% → 20-40
            score = 20 + (abs(return_pct) - 10) / 5 * 20
            return {
                "score": score,
                "reason": f"Weak downtrend ({return_pct:.1f}% 12M return)",
                "details": {"current": current_price, "12m_ago": price_12m_ago, "return_pct": return_pct},
            }
        elif return_pct >= -25:
            # Scale -25% to -10% → 10-20
            score = 10 + (abs(return_pct) - 25) / 15 * 10
            return {
                "score": score,
                "reason": f"Strong downtrend ({return_pct:.1f}% 12M return)",
                "details": {"current": current_price, "12m_ago": price_12m_ago, "return_pct": return_pct},
            }
        else:
            return {
                "score": 0,
                "reason": f"Severe downtrend ({return_pct:.1f}% 12M return)",
                "details": {"current": current_price, "12m_ago": price_12m_ago, "return_pct": return_pct},
            }
