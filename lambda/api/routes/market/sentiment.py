"""Handler for /api/market/sentiment.

Split out of lambda/api/routes/market.py 2026-09-05 (file-size-ratchet decomposition).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from psycopg2.extensions import cursor
from routes.utils import check_data_freshness, json_response, raise_db_error, safe_json_serialize

from ._shared import _parse_range_param

logger = logging.getLogger(__name__)


def _handle_sentiment(cur: cursor, params: dict[str, Any] | None) -> Any:
    """Handle /api/market/sentiment endpoint."""
    range_days = _parse_range_param(params) if params else 30
    sentiment_data = {}
    cutoff_date = (datetime.now(timezone.utc) - timedelta(days=range_days)).date()

    # OPTIMIZATION: Set timeout to prevent slow queries from blocking
    cur.execute("SET LOCAL statement_timeout = '4000ms'")

    # AAII investor sentiment
    try:
        cur.execute(
            """
            SELECT date, bullish, neutral, bearish
            FROM aaii_sentiment
            WHERE date >= %s
            ORDER BY date ASC
            LIMIT 100
        """,
            (cutoff_date,),
        )
        aaii_rows = [safe_json_serialize(dict(r)) for r in cur.fetchall()]
        aaii_current = aaii_rows[-1] if aaii_rows else None

        # Compute trend: is bullish rising or falling?
        aaii_trend = "neutral"
        if len(aaii_rows) >= 2:
            prev_bull = aaii_rows[-2].get("bullish")
            curr_bull = aaii_rows[-1].get("bullish")
            if prev_bull is not None and curr_bull is not None:
                prev = float(prev_bull)
                curr = float(curr_bull)
                if curr > prev * 1.02:
                    aaii_trend = "rising"
                elif curr < prev * 0.98:
                    aaii_trend = "falling"
                else:
                    aaii_trend = "neutral"

        sentiment_data["aaii"] = {
            "current": aaii_current,
            "history": aaii_rows,
            "trend": aaii_trend,
            "data": aaii_rows,
            "bullish_pct": (
                float(aaii_current.get("bullish")) if aaii_current and aaii_current.get("bullish") is not None else None
            ),
        }
    except (ValueError, ZeroDivisionError, TypeError) as e:
        logger.error(f"[SENTIMENT_AAII] Error: {type(e).__name__}")
        raise_db_error(e, "AAII sentiment query")

    # NAAIM manager exposure
    try:
        cur.execute(
            """
            SELECT date, naaim_number_mean, bullish, bearish
            FROM naaim
            WHERE date >= %s
            ORDER BY date ASC
            LIMIT 52
        """,
            (cutoff_date,),
        )
        naaim_rows = [safe_json_serialize(dict(r)) for r in cur.fetchall()]
        naaim_current = naaim_rows[-1] if naaim_rows else None

        # Compute trend
        naaim_trend = "neutral"
        if len(naaim_rows) >= 2:
            prev_mean = naaim_rows[-2].get("naaim_number_mean")
            curr_mean = naaim_rows[-1].get("naaim_number_mean")
            if prev_mean is not None and curr_mean is not None:
                prev = float(prev_mean)
                curr = float(curr_mean)
                if curr > prev * 1.02:
                    naaim_trend = "rising"
                elif curr < prev * 0.98:
                    naaim_trend = "falling"
                else:
                    naaim_trend = "neutral"

        sentiment_data["naaim"] = {
            "current": (
                float(naaim_current.get("naaim_number_mean"))
                if naaim_current and naaim_current.get("naaim_number_mean") is not None
                else None
            ),
            "history": naaim_rows,
            "trend": naaim_trend,
            "bullish_pct": (
                float(naaim_current.get("bullish"))
                if naaim_current and naaim_current.get("bullish") is not None
                else None
            ),
            "bearish_pct": (
                float(naaim_current.get("bearish"))
                if naaim_current and naaim_current.get("bearish") is not None
                else None
            ),
        }
    except (ValueError, ZeroDivisionError, TypeError) as e:
        logger.error(f"[SENTIMENT_NAAIM] Error: {type(e).__name__}")
        raise_db_error(e, "NAAIM sentiment query")

    # Fear & Greed
    try:
        cur.execute(
            """
            SELECT date, fear_greed_value as value, fear_greed_label as label
            FROM fear_greed_index
            WHERE date >= %s
            ORDER BY date ASC
            LIMIT 100
        """,
            (cutoff_date,),
        )
        fg_rows = [safe_json_serialize(dict(r)) for r in cur.fetchall()]
        fg_current = fg_rows[-1] if fg_rows else None

        # Compute trend
        fg_trend = "neutral"
        if len(fg_rows) >= 2:
            prev_val = fg_rows[-2].get("value")
            curr_val = fg_rows[-1].get("value")
            if prev_val is not None and curr_val is not None:
                prev = float(prev_val)
                curr = float(curr_val)
                if curr < prev * 0.98:
                    fg_trend = "rising_fear"
                elif curr > prev * 1.02:
                    fg_trend = "rising_greed"
                else:
                    fg_trend = "neutral"

        sentiment_data["fearGreed"] = {
            "current": {
                "value": (float(fg_current["value"]) if fg_current and fg_current.get("value") is not None else None),
                "label": fg_current.get("label") if fg_current else None,
            },
            "history": fg_rows,
            "trend": fg_trend,
            "data": fg_rows,
        }
    except (ValueError, ZeroDivisionError, TypeError) as e:
        logger.error(f"[SENTIMENT_FG] Error: {type(e).__name__}")
        raise_db_error(e, "fear/greed sentiment query")

    freshness = check_data_freshness(cur, "aaii_sentiment", "date", warning_days=1)
    return json_response(200, sentiment_data, data_freshness=freshness)
