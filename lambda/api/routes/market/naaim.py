"""Handler for /api/market/naaim.

Split out of lambda/api/routes/market.py 2026-09-05 (file-size-ratchet decomposition).
"""

from __future__ import annotations

import logging
from typing import Any

from psycopg2.extensions import cursor
from routes.utils import error_response, json_response, raise_api_error, raise_db_error

logger = logging.getLogger(__name__)


def _handle_naaim(cur: cursor) -> Any:
    """Handle /api/market/naaim endpoint."""
    try:
        cur.execute("SET LOCAL statement_timeout = '5000ms'")
        cur.execute("""
            SELECT date, naaim_number_mean, bullish, bearish
            FROM naaim
            ORDER BY date ASC
            LIMIT 52
        """)
        rows = cur.fetchall()
        if not rows:
            return error_response(503, "no_data", "NAAIM data not yet available")

        history = []
        for r in rows:
            r_dict = dict(r)
            naaim_val = r_dict.get("naaim_number_mean")
            bullish_val = r_dict.get("bullish")
            bearish_val = r_dict.get("bearish")
            date_val = r_dict.get("date")
            if date_val is None:
                logger.error(f"[NAAIM] Record missing date: {list(r_dict.keys())}")
                raise_api_error(500, "data_integrity_error", "NAAIM record missing date field")
            history.append(
                {
                    "date": str(date_val),
                    "value": (float(naaim_val) if naaim_val is not None else None),
                    "bullish_pct": (float(bullish_val) if bullish_val is not None else None),
                    "bearish_pct": (float(bearish_val) if bearish_val is not None else None),
                }
            )

        if history:
            current = history[-1]
            values: list[float] = [float(h["value"]) for h in history if h["value"] is not None]

            # Compute moving averages
            ma_10 = sum(values[-10:]) / min(10, len(values)) if len(values) >= 10 else None
            ma_20 = sum(values[-20:]) / min(20, len(values)) if len(values) >= 20 else None
            ma_50 = sum(values[-50:]) / min(50, len(values)) if len(values) >= 50 else None

            # Identify extremes (>80 = extreme bullish, <20 = extreme bearish)
            _cv = current["value"]
            curr_val: float | None = float(_cv) if _cv is not None else None
            signals = {
                "extreme_bullish": (curr_val > 80 if curr_val is not None else None),
                "extreme_bearish": (curr_val < 20 if curr_val is not None else None),
                "overbought": curr_val > 70 if curr_val is not None else None,
                "oversold": curr_val < 30 if curr_val is not None else None,
                "above_50": curr_val > 50 if curr_val is not None else None,
                "below_50": curr_val <= 50 if curr_val is not None else None,
            }

            return json_response(
                200,
                {
                    "current": current["value"],
                    "bullish_pct": current["bullish_pct"],
                    "bearish_pct": current["bearish_pct"],
                    "history": history,
                    "moving_averages": {
                        "ma_10": round(ma_10, 2) if ma_10 else None,
                        "ma_20": round(ma_20, 2) if ma_20 else None,
                        "ma_50": round(ma_50, 2) if ma_50 else None,
                    },
                    "signals": signals,
                    "interpretation": {
                        "meaning": "Manager equity allocation %; 0=all cash, 100=fully invested",
                        "current_stance": ("bullish" if curr_val is not None and curr_val > 50 else "bearish"),
                        "extremity": (
                            "extreme_bullish"
                            if curr_val is not None and curr_val > 80
                            else ("extreme_bearish" if curr_val is not None and curr_val < 20 else "normal")
                        ),
                    },
                },
            )
        else:
            return error_response(503, "no_data", "NAAIM data processing failed")
    except (ValueError, ZeroDivisionError, TypeError) as e:
        logger.error(f"[NAAIM] Error: {type(e).__name__}")
        raise_db_error(e, "NAAIM query")
        raise  # unreachable - raise_db_error is NoReturn; satisfies mypy without lambda path config
