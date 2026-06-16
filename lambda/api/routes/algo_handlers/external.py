"""Route: algo"""

import psycopg2
import psycopg2.extras
import psycopg2.errors
import psycopg2.sql
from typing import Dict
import logging
import re
import json
import os
from datetime import datetime, timedelta, date, timezone
import boto3
from botocore.exceptions import ClientError
from pydantic import ValidationError

# Ensure imports work - setup_imports is imported by parent module (lambda_function or api_router)
from routes.utils import (
    error_response,
    success_response,
    list_response,
    json_response,
    safe_limit,
    safe_days,
    safe_offset,
    handle_db_error,
    db_route_handler,
    check_data_freshness,
    safe_json_serialize,
    safe_dict_convert,
    normalize_to_utc_datetime,
)

from utils.rate_limiting import (
    check_admin_rate_limit,
    ADMIN_RATE_LIMITS,
    check_public_rate_limit,
    PUBLIC_RATE_LIMITS,
)
from utils.validation import (
    safe_float,
    safe_float_strict,
    safe_int,
    safe_int_strict,
    APIResponseValidator,
)
from models.requests import TradePreviewRequest, PreTradeImpactRequest
import math

logger = logging.getLogger(__name__)



@db_route_handler("get economic calendar")
def _get_economic_calendar(cur) -> Dict:
    """Get economic calendar data with freshness validation.

    Returns list of upcoming economic events. Includes data_freshness metadata
    so clients can detect when calendar data is stale or missing.
    """
    try:
        freshness = check_data_freshness(
            cur, "economic_calendar", "event_date", warning_days=7
        )

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
    except Exception as e:
        logger.error(f"Economic calendar fetch error: {type(e).__name__}: {e}")
        return error_response(
            503, "service_unavailable", "Economic calendar unavailable"
        )



@db_route_handler("get sentiment")
def _get_sentiment(cur) -> Dict:
    """Get market sentiment data.

    Returns current market sentiment (fear/greed index). Returns 503 error
    if data is unavailable or incomplete, enabling clients to handle data
    absence explicitly rather than displaying stale defaults.
    """
    freshness = check_data_freshness(cur, "market_sentiment", "date", warning_days=1)

    cur.execute("""
        SELECT date, fear_greed_index, label
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
    label = data.get("label")

    if fear_greed is None or label is None:
        logger.warning(
            f"Sentiment data incomplete: fear_greed={fear_greed}, label={label}"
        )
        return error_response(503, "service_unavailable", "Sentiment data incomplete")

    return success_response(
        {
            "date": data.get("date"),
            "fear_greed_index": safe_float(fear_greed),
            "label": label,
            "data_freshness": freshness,
        }
    )



