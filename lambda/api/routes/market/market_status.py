"""Handler for /api/market and /api/market/status.

Split out of lambda/api/routes/market.py 2026-09-05 (file-size-ratchet decomposition).
"""

from __future__ import annotations

import logging
from typing import Any

from psycopg2.extensions import cursor
from routes.utils import check_data_freshness, json_response, raise_api_error, safe_json_serialize

from shared_contracts.response_validator import ResponseValidator

logger = logging.getLogger(__name__)


def _handle_market_status(cur: cursor) -> Any:
    """Handle /api/market and /api/market/status endpoints."""
    cur.execute("SET LOCAL statement_timeout = '5000ms'")
    cur.execute("""
        SELECT date, market_trend, market_stage, advance_decline_ratio,
                   new_highs_count, new_lows_count, vix_level, put_call_ratio
        FROM market_health_daily
        ORDER BY date DESC
        LIMIT 1
    """)
    row = cur.fetchone()
    if not row:
        raise_api_error(503, "no_data", "Market status data not yet available")

    result = safe_json_serialize(dict(row))

    # Add freshness check
    freshness = check_data_freshness(cur, "market_health_daily", "date", warning_days=1)

    is_valid, error_msg = ResponseValidator.validate_endpoint_response("market/status", result)
    if not is_valid:
        logger.error(f"Market status response validation failed: {error_msg}")
        raise_api_error(500, "response_validation_error", error_msg or "Market status validation failed")

    return json_response(200, result, data_freshness=freshness)
