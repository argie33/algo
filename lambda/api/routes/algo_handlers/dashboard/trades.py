"""Algo dashboard handler: /api/algo/trades.

Split 2026-09-05 out of the original 2160-line algo_handlers/dashboard.py (see
positions.py's module docstring for the full split rationale). This module holds only
`_get_algo_trades`. Pure move, no logic changed.
"""

from __future__ import annotations

import logging
from typing import Any

from psycopg2.extensions import cursor
from routes.utils import (
    check_data_freshness,
    db_route_handler,
    json_response,
    safe_dict_convert,
    safe_json_serialize,
    validate_api_response,
)

from utils.validation import APIResponseValidator

logger = logging.getLogger(__name__)


@db_route_handler("fetch algo trades")
@validate_api_response("trades")
def _get_algo_trades(cur: cursor, limit: int = 200, user_id: str | None = None, status: str | None = None) -> Any:
    """Get recent trades with all fields for frontend.

    Scoped to user if user_id provided, filtered by status if provided.
    """
    where_parts: list[str] = []
    params: list[Any] = []

    if user_id:
        where_parts.append("cognito_sub = %s")
        params.append(user_id)

    if status:
        # Validate status parameter to prevent SQL injection
        valid_statuses = ["open", "closed", "halted", "cancelled"]
        if status not in valid_statuses:
            logger.warning(f"Invalid trade status requested: {status}, ignoring filter")
            status = None
        else:
            where_parts.append("status = %s")
            params.append(status)

    where_clause = "WHERE " + " AND ".join(where_parts) if where_parts else ""
    params.append(limit)

    cur.execute(
        f"""
            SELECT trade_id, symbol, signal_date, trade_date, entry_price, entry_time,
                   entry_quantity, entry_reason, exit_price, exit_date, exit_time,
                   exit_reason, exit_r_multiple, profit_loss_dollars, profit_loss_pct,
                   status, base_type, stage_phase,
                   trade_duration_days, mfe_pct, mae_pct, created_at
            FROM algo_trades
            {where_clause}
            ORDER BY COALESCE(exit_date, trade_date) DESC, trade_id DESC
            LIMIT %s
        """,
        params,
    )
    trades = cur.fetchall()
    items = [safe_json_serialize(safe_dict_convert(t)) for t in trades]
    freshness = check_data_freshness(cur, "algo_trades", "created_at", warning_days=1)
    response_data = {
        "items": items,
        "pagination": {"total": len(items), "limit": limit, "offset": 0},
    }
    sanitized = APIResponseValidator.sanitize_response(response_data)

    # FIX: Pass freshness separately to json_response so it's included in response
    return json_response(200, sanitized, data_freshness=freshness)
