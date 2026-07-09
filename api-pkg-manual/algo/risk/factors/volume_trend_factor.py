#!/usr/bin/env python3
"""Volume trend factor strategy for market exposure calculation."""

import logging
from typing import Any

from algo.risk.market_factor_strategy import MarketFactorStrategy

logger = logging.getLogger(__name__)


class VolumeTrendFactor(MarketFactorStrategy):
    """Market participation quality factor: volume trend over recent period.

    Measures whether volume is supporting price moves (strong participation)
    or if volume is waning (deteriorating participation quality).
    Weight: 4 points
    """

    @property
    def name(self) -> str:
        return "volume_trend"

    @property
    def weight(self) -> float:
        return 4.0  # 4 out of 100 total weight

    def calculate(self, eval_date: Any, cur: Any) -> dict[str, Any]:
        """Calculate market volume quality trend (10-day vs 50-day average).

        Scoring based on recent vs historical volume:
        - Recent > 50-day avg + rising = 100 (strong participation)
        - Recent > 50-day avg = 70 (above average)
        - Recent ~= 50-day avg = 50 (neutral)
        - Recent < 50-day avg = 30 (below average)
        - Recent < 50-day avg + declining = 0 (weak participation)

        Raises ValueError if volume data unavailable.
        """
        try:
            cur.execute(
                """
                SELECT
                    AVG(volume) FILTER (
                        WHERE date > %s::date - INTERVAL '10 days' AND date <= %s
                    ) as vol_10d_avg,
                    AVG(volume) FILTER (
                        WHERE date > %s::date - get_interval_sql('50d') AND date <= %s
                    ) as vol_50d_avg,
                    MAX(volume) FILTER (
                        WHERE date > %s::date - INTERVAL '10 days' AND date <= %s
                    ) as vol_recent_peak
                FROM price_daily
                WHERE symbol = 'SPY'
                """,
                (eval_date, eval_date, eval_date, eval_date, eval_date, eval_date),
            )
            row = cur.fetchone()
            if not row or row[0] is None or row[1] is None:
                raise ValueError("Volume trend factor: insufficient volume data")

            vol_10d_avg = float(row[0])
            vol_50d_avg = float(row[1])
            if row[2] is None:
                raise ValueError(
                    "Volume trend factor: recent volume peak data (last 10 days) unavailable. "
                    "Cannot assess volume trend quality without complete price/volume history."
                )
            vol_recent_peak = float(row[2])

            if vol_50d_avg <= 0:
                raise ValueError("Volume trend factor: invalid historical volume")

            vol_ratio = vol_10d_avg / vol_50d_avg
            is_rising = vol_recent_peak > vol_10d_avg * 1.1

            # Scoring based on volume ratio and trend
            if vol_ratio > 1.1 and is_rising:
                score = 100.0
                signal = "strong_participation"
            elif vol_ratio > 1.05:
                score = 70.0
                signal = "above_average"
            elif vol_ratio >= 0.95:
                score = 50.0
                signal = "neutral_participation"
            elif vol_ratio >= 0.85:
                score = 30.0
                signal = "below_average"
            else:
                score = 0.0
                signal = "weak_participation"

            return {
                "score": score,
                "reason": f"Volume trend: {vol_ratio:.2f}x 50-day avg ({signal})",
                "details": {
                    "vol_10d_avg": vol_10d_avg,
                    "vol_50d_avg": vol_50d_avg,
                    "vol_ratio": vol_ratio,
                    "is_rising": is_rising,
                    "signal": signal,
                },
            }
        except Exception as e:
            logger.warning(f"Volume trend calculation failed: {e}")
            raise ValueError(f"Volume trend factor: {e}") from e
