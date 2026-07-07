"""Route: algo"""

from __future__ import annotations

import logging
from typing import Any

import psycopg2
import psycopg2.errors
import psycopg2.extras
import psycopg2.sql
from psycopg2.extensions import cursor

# Ensure imports work - setup_imports is imported by parent module (lambda_function or api_router)
from routes.utils import (
    check_data_freshness,
    db_route_handler,
    error_response,
    handle_db_error,
    list_response,
    safe_dict_convert,
    safe_json_serialize,
    success_response,
    validate_api_response,
)

logger = logging.getLogger(__name__)


@db_route_handler("get economic calendar")

@validate_api_response("econ_cal")

def _get_economic_calendar(cur: cursor) -> Any:
    """Get economic calendar data with freshness validation.

    Returns list of upcoming economic events. Includes data_freshness metadata
    so clients can detect when calendar data is stale or missing.
    """
    try:
        freshness = check_data_freshness(cur, "economic_calendar", "event_date", warning_days=7)

        cur.execute("""
            SELECT event_date, event_name, country, importance,
                   category, event_time,
                   forecast_value AS forecast,
                   actual_value AS actual,
                   previous_value AS previous
            FROM economic_calendar
            WHERE event_date >= CURRENT_DATE
            ORDER BY event_date ASC
            LIMIT 100
        """)
        rows = cur.fetchall()
        events = [safe_json_serialize(safe_dict_convert(r)) for r in rows]

        if freshness.get("is_stale"):
            logger.warning(f"Economic calendar stale: {freshness.get('warning')}")

        return list_response(events, total=len(events), data_freshness=freshness)
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        code, error_type, message = handle_db_error(e, "get economic calendar")
        return error_response(code, error_type, message)


@db_route_handler("get sentiment")

@validate_api_response("sentiment")

def _get_sentiment(cur: cursor) -> Any:
    """Get market sentiment data.

    Returns current market sentiment (fear/greed index). Returns 503 error
    if data is unavailable or incomplete, enabling clients to handle data
    absence explicitly rather than displaying stale defaults.
    """
    freshness = check_data_freshness(cur, "market_sentiment", "date", warning_days=1)

    cur.execute("""
        SELECT date, fear_greed_index, sentiment_score, bullish_pct, bearish_pct, neutral_pct
        FROM market_sentiment
        ORDER BY date DESC
        LIMIT 1
    """)
    row = cur.fetchone()

    if row is None:
        logger.warning("Sentiment data missing: market_sentiment table is empty")
        return error_response(503, "service_unavailable", "Sentiment data unavailable")

    data = safe_dict_convert(row)
    fear_greed = data.get("fear_greed_index")
    sentiment_score = data.get("sentiment_score")

    if fear_greed is None:
        logger.warning(f"Sentiment data incomplete: fear_greed={fear_greed}")
        return error_response(503, "service_unavailable", "Sentiment data incomplete")

    return success_response(
        {
            "date": data.get("date"),
            "fear_greed_index": float(fear_greed),
            "sentiment_score": float(sentiment_score) if sentiment_score is not None else None,
            "bullish_pct": data.get("bullish_pct"),
            "bearish_pct": data.get("bearish_pct"),
            "neutral_pct": data.get("neutral_pct"),
            "data_freshness": freshness,
        }
    )
