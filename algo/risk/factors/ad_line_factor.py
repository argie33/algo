#!/usr/bin/env python3
"""Advance/decline line factor strategy for market exposure calculation."""

import logging
from typing import Any

from algo.risk.market_factor_strategy import MarketFactorStrategy

logger = logging.getLogger(__name__)


class ADLineFactor(MarketFactorStrategy):
    """Market confirmation factor: advance/decline line vs SPY direction.

    Measures whether breadth (advancers-decliners) confirms or diverges
    from price direction over 20 days.
    Weight: 6 points
    """

    @property
    def name(self) -> str:
        return "ad_line"

    @property
    def weight(self) -> float:
        return 6.0  # 6 out of 100 total weight

    def calculate(self, eval_date: Any, cur: Any) -> dict[str, Any]:
        """Calculate market confirmation from A/D line vs SPY.

        Scoring based on confirmation/divergence:
        - Both A/D and SPY rising = 100 (confirming uptrend)
        - A/D rising, SPY falling = 60 (hidden bullish divergence)
        - Both falling, or A/D falling, SPY rising = 30 (bearish divergence)

        Raises ValueError if breadth or price data unavailable.
        """
        try:
            cur.execute(
                """
                WITH mh AS (
                    SELECT date, advance_decline_ratio
                    FROM market_health_daily
                    WHERE date <= %s AND advance_decline_ratio IS NOT NULL
                    ORDER BY date DESC LIMIT 22
                ),
                spy AS (
                    SELECT date, close FROM price_daily
                    WHERE symbol = 'SPY' AND date <= %s
                    ORDER BY date DESC LIMIT 22
                )
                SELECT mh.date, mh.advance_decline_ratio AS ratio, spy.close AS spy_close
                FROM mh
                JOIN spy ON mh.date = spy.date
                ORDER BY mh.date ASC
                """,
                (eval_date, eval_date),
            )
            rows = cur.fetchall()
            if len(rows) < 5:
                raise ValueError("AD line factor: insufficient historical data for confirmation analysis")

            # Compute A/D cumulative change using ratio -> net = (ratio-1)/(ratio+1)
            nets = []
            for r in rows:
                ratio = float(r[1])
                if ratio is None:
                    raise ValueError("A/D ratio missing - cannot calculate confirmation")
                nets.append((ratio - 1) / (ratio + 1))

            first_net = nets[0]
            last_net = nets[-1]
            ad_change = last_net - first_net

            first_spy = float(rows[0][2])
            last_spy = float(rows[-1][2])
            if first_spy <= 0:
                raise ValueError(
                    f"A/D line factor: Invalid first SPY price ({first_spy}) — price must be positive for change calculation"
                )
            spy_change_pct = (last_spy - first_spy) / first_spy * 100.0

            # Determine confirmation or divergence
            if (ad_change > 0 and spy_change_pct > 0) or (ad_change < 0 and spy_change_pct < 0):
                score = 100.0
                relation = "confirming"
            elif ad_change > 0 and spy_change_pct < 0:
                score = 60.0
                relation = "bullish_divergence"
            else:
                score = 30.0
                relation = "bearish_divergence"

            return {
                "score": score,
                "reason": f"A/D confirmation: {relation}",
                "details": {
                    "ad_change_20d": ad_change,
                    "spy_change_pct_20d": spy_change_pct,
                    "relation": relation,
                },
            }
        except Exception as e:
            logger.warning(f"A/D line calculation failed: {e}")
            raise ValueError(f"A/D line factor: {e}") from e
