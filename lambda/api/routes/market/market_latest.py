"""Handler for /api/market/latest.

Split out of lambda/api/routes/market.py 2026-09-05 (file-size-ratchet decomposition).
"""

from __future__ import annotations

from typing import Any

from psycopg2.extensions import cursor
from routes.utils import db_route_handler, json_response, safe_json_serialize


@db_route_handler("get market latest")
def _get_market_latest(cur: cursor) -> Any:
    cur.execute("""
        SELECT date, market_trend, market_stage, advance_decline_ratio,
                   new_highs_count, new_lows_count, vix_level, put_call_ratio,
                   up_volume_percent, breadth_momentum_10d
        FROM market_health_daily
        ORDER BY date DESC
        LIMIT 1
    """)
    market_row = cur.fetchone()

    cur.execute("""
        SELECT date, fear_greed_value, fear_greed_label
        FROM fear_greed_index
        ORDER BY date DESC
        LIMIT 1
    """)
    sentiment_row = cur.fetchone()

    cur.execute("""
        SELECT symbol, close
        FROM price_daily
        WHERE date = (SELECT date FROM price_daily ORDER BY date DESC LIMIT 1)
        ORDER BY symbol
        LIMIT 10
    """)
    recent_prices = cur.fetchall()

    result: dict[str, Any] = {}
    if market_row:
        result["market"] = dict(market_row)
    if sentiment_row:
        result["sentiment"] = dict(sentiment_row)
    if recent_prices:
        result["prices"] = [safe_json_serialize(dict(p)) for p in recent_prices]

    # FAIL-FAST: Require at least market data; don't return empty response
    if not market_row:
        return json_response(
            503,
            {
                "isDataError": True,
                "message": "Market data unavailable",
                "available": list(result.keys()),
            },
        )

    return json_response(200, result)
