"""Route: options - CSP/covered-call candidate screener (goal session 2026-09-12 POC).

Reads scripts/options_data_loader.py's output (options_chains.delta, self-computed via
Black-Scholes from vendor IV - see utils/options/black_scholes.py). This is a daily
rotating-sample data source (terraform/modules/loaders/main.tf's options_data_loader ECS
task, 05:30 UTC - written 2026-09-12, not yet applied), not a full-universe/intraday feed,
so data_freshness on this endpoint will often show a given symbol as several days stale
relative to other, continuously-refreshed dashboard endpoints - that's expected at this
stage, not a bug.
"""

from __future__ import annotations

import logging
from typing import Any

import psycopg2
import psycopg2.errors
from psycopg2.extensions import cursor
from routes.utils import (
    check_data_freshness,
    error_response,
    execute_with_timeout,
    handle_db_error,
    list_response,
    safe_json_serialize,
)

logger = logging.getLogger(__name__)

# 0.15-0.30 delta zone: the commonly-targeted CSP/covered-call strike band (see this
# session's literature review - not academically validated as optimal, just the
# conventional screening band; our own delta/DTE choices still need out-of-sample
# validation before being trusted as a strategy, this endpoint is a screener, not advice).
_CANDIDATE_DELTA_LOW = 0.15
_CANDIDATE_DELTA_HIGH = 0.30


def handle(
    cur: cursor,
    path: str,
    method: str,
    params: dict[str, Any],
    body: dict[str, Any] | None = None,
    jwt_claims: dict[str, Any] | None = None,
) -> Any:
    """Handle /api/options and /api/options/* endpoints."""
    try:
        if path in ("/api/options", "/api/options/candidates"):
            return _get_candidates(cur, params)
        return error_response(404, "not_found", f"No options handler for {path}")
    except (
        psycopg2.errors.QueryCanceled,
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        TimeoutError,
        Exception,
    ) as e:
        logger.error(
            f"Options route error in {path} - {type(e).__name__}: {e}", extra={"operation": "get options candidates"}
        )
        code, error_type, message = handle_db_error(e, "get options candidates")
        return error_response(code, error_type, message)


def _get_candidates(cur: cursor, params: dict[str, Any]) -> Any:
    """CSP (put) and covered-call (call) candidates in the 0.15-0.30 delta zone, most
    recent quote_date per symbol. Optional ?symbol=AAPL to filter to one symbol."""
    symbol = params.get("symbol")

    rows = execute_with_timeout(
        cur,
        """
        WITH latest_quote AS (
            SELECT symbol, MAX(quote_date) AS quote_date
            FROM options_chains
            WHERE (%(symbol)s::text IS NULL OR symbol = %(symbol)s)
            GROUP BY symbol
        )
        SELECT
            oc.symbol, oc.contract_symbol, oc.option_type, oc.strike_price,
            oc.expiration_date, oc.bid, oc.ask, oc.last_price, oc.volume,
            oc.open_interest, oc.quote_date, oc.iv, oc.days_to_expiration, oc.delta
        FROM options_chains oc
        JOIN latest_quote lq ON lq.symbol = oc.symbol AND lq.quote_date = oc.quote_date
        WHERE ABS(oc.delta) BETWEEN %(delta_low)s AND %(delta_high)s
        ORDER BY oc.symbol, oc.option_type, oc.strike_price DESC
        LIMIT 500
        """,
        {
            "symbol": symbol,
            "delta_low": _CANDIDATE_DELTA_LOW,
            "delta_high": _CANDIDATE_DELTA_HIGH,
        },
        timeout_sec=5,
    )

    freshness = check_data_freshness(cur, "options_chains", "quote_date", warning_days=3)
    return list_response(
        [safe_json_serialize(dict(r)) for r in rows] if rows else [],
        data_freshness=freshness,
    )
