"""Handler for /api/market/trends.

Split out of lambda/api/routes/market.py 2026-09-05 (file-size-ratchet decomposition).
"""

from __future__ import annotations

from typing import Any

from psycopg2.extensions import cursor
from routes.utils import db_route_handler, list_response

_TREND_DIRECTION_TO_TYPE = {"up": "uptrend", "down": "downtrend", "sideways": "consolidation"}


@db_route_handler("get market trend health")
def _get_trend_health(cur: cursor) -> Any:
    """Handle /api/market/trends endpoint.

    BUG FOUND 2026-08-10 (frontend/dashboard audit pass): MarketsHealth.jsx's TrendHealthCard
    has called this exact path on a 5-minute poll since it was written, but this handler never
    existed - every load showed "Trend data unavailable". trend_template_data's own
    trend_direction values ("up"/"down"/"sideways") don't match what the frontend filters for
    ("uptrend"/"downtrend"/"consolidation"), so a straight passthrough wouldn't have worked even
    with a handler present - mapped explicitly here. days_in_trend (avg trend age) is
    deliberately omitted: computing consecutive-same-direction days per symbol needs a
    window-function pass this endpoint doesn't do yet; the frontend already treats it as
    optional (`t.days_in_trend != null` filter, avgAge is null with none present).
    """
    cur.execute("""
        WITH latest AS (
            SELECT symbol, trend_direction
            FROM trend_template_data
            WHERE date = (SELECT MAX(date) FROM trend_template_data)
              AND trend_direction IS NOT NULL
              AND symbol NOT IN (SELECT symbol FROM etf_symbols)
        )
        SELECT symbol, trend_direction FROM latest
    """)
    rows = cur.fetchall()
    items = [
        {"symbol": r["symbol"], "trend_type": _TREND_DIRECTION_TO_TYPE.get(r["trend_direction"]), "days_in_trend": None}
        for r in rows
        if r["trend_direction"] in _TREND_DIRECTION_TO_TYPE
    ]
    return list_response(items)
