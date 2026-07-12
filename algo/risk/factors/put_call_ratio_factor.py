#!/usr/bin/env python3
"""Put/call ratio factor strategy for market exposure calculation."""

import logging
from typing import Any

from algo.risk.market_factor_strategy import MarketFactorStrategy

logger = logging.getLogger(__name__)


class PutCallRatioFactor(MarketFactorStrategy):
    """Options market sentiment factor: put/call ratio contrarian indicator.

    High P/C ratio (>1.1): elevated put buying = fear/hedging = contrarian bullish.
    Low P/C ratio (<0.6): call-heavy = complacency/greed = contrarian bearish.
    Weight: 8 points
    """

    @property
    def name(self) -> str:
        return "put_call_ratio"

    @property
    def weight(self) -> float:
        return 8.0  # 8 out of 100 total weight

    def calculate(self, eval_date: Any, cur: Any) -> dict[str, Any]:
        """Calculate contrarian options sentiment from put/call ratio.

        Scoring (contrarian):
        - P/C > 1.2 = 100 (extreme fear -> buy signal)
        - P/C 0.9-1.2 = 80 (elevated hedging)
        - P/C 0.7-0.9 = 65 (neutral)
        - P/C 0.5-0.7 = 40 (complacent)
        - P/C < 0.5 = 20 (extreme greed -> caution)

        Put/call ratio is HIGH-priority enrichment (8pt factor).
        Raises ValueError if data is missing (fail-fast pattern).
        """
        try:
            cur.execute(
                """
                SELECT put_call_ratio FROM market_health_daily
                WHERE date <= %s AND put_call_ratio IS NOT NULL
                ORDER BY date DESC LIMIT 1
                """,
                (eval_date,),
            )
            row = cur.fetchone()
            if not row:
                raise ValueError(
                    f"Put/call ratio factor: no data available for {eval_date} - "
                    f"market_health_daily missing put_call_ratio readings"
                )

            # Support both DictCursor (row is dict) and tuple cursor (row is tuple)
            if isinstance(row, dict):
                pcr_val = row.get('put_call_ratio')
            else:
                pcr_val = row[0]

            if pcr_val is None:
                raise ValueError(
                    f"Put/call ratio factor: no data available for {eval_date} - "
                    f"market_health_daily missing put_call_ratio readings"
                )

            pcr = float(pcr_val)

            # Contrarian scoring
            if pcr > 1.2:
                score = 100.0
                signal = "extreme_fear"
            elif pcr > 0.9:
                score = 80.0
                signal = "elevated_hedging"
            elif pcr > 0.7:
                score = 65.0
                signal = "neutral"
            elif pcr > 0.5:
                score = 40.0
                signal = "complacent"
            else:
                score = 20.0
                signal = "extreme_greed"

            return {
                "score": score,
                "reason": f"Put/call ratio: {pcr:.3f} ({signal})",
                "details": {"put_call_ratio": pcr, "signal": signal},
            }
        except Exception as e:
            logger.warning(f"Put/call ratio calculation failed: {e}")
            raise ValueError(f"Put/call ratio factor: {e}") from e
