"""Route: trades"""

from __future__ import annotations

import hashlib
import json as _json
import logging
import uuid
from datetime import date, datetime, timezone
from typing import Any, cast

import psycopg2
import psycopg2.errors
import psycopg2.extras
import psycopg2.sql
from auth_utils import check_admin_access
from models.requests import ManualTradeRequest
from psycopg2.extensions import cursor
from pydantic import ValidationError
from routes.utils import (
    check_data_freshness,
    error_response,
    extract_param,
    handle_db_error,
    json_response,
    list_response,
    raise_api_error,
    raise_db_error,
    safe_json_serialize,
    safe_limit,
    safe_offset,
)

from shared_contracts.response_validator import ResponseValidator
from utils.data_queries import count_trades_by_status, get_trades_by_status

logger = logging.getLogger(__name__)


def _compute_request_signature(idempotency_key: str, body: dict[str, Any]) -> str:
    """Compute a hash of the idempotency key and request body.

    Returns a deterministic signature to detect duplicate requests.
    """
    content = _json.dumps({"key": idempotency_key, "body": body}, sort_keys=True)
    return hashlib.sha256(content.encode()).hexdigest()


def _check_idempotency(cur: cursor, signature: str) -> dict[str, Any]:
    """Check if this request signature has been processed before.

    Returns the cached response if found, or marker dict indicating cache miss.

    Returns:
        Cached response dict with cached_response=True, or {"cached_response": False} if not found
    """
    try:
        cur.execute(
            """
            SELECT response_data, created_at FROM api_idempotency_cache
            WHERE request_signature = %s AND created_at > NOW() - INTERVAL '24 hours'
            LIMIT 1
            """,
            (signature,),
        )
        row = cur.fetchone()
        if row:
            cached = dict(_json.loads(row[0]))
            cache_age_seconds = (datetime.now(timezone.utc) - row[1]).total_seconds()
            if cache_age_seconds > 86400:  # 24 hours
                logger.warning(
                    f"[IDEMPOTENCY] Cache TTL exceeded: {cache_age_seconds}s > 86400s. Rejecting stale cache."
                )
                return {"cached_response": False}
            cached["cached_response"] = True
            return cached
        return {"cached_response": False}
    except (psycopg2.Error, _json.JSONDecodeError) as e:
        raise RuntimeError(
            f"IDEMPOTENCY INFRASTRUCTURE FAILURE: Cannot check idempotency cache: {type(e).__name__}: {e}. "
            f"Duplicate trade protection unavailable."
        ) from e


def _store_idempotent_response(cur: cursor, signature: str, response: dict[str, Any]) -> None:
    """Cache the response for this idempotent request signature.

    Raises:
        RuntimeError: If cache write fails. Duplicate trade protection requires caching.
    """
    try:
        cur.execute(
            """
            INSERT INTO api_idempotency_cache (request_signature, response_data, created_at)
            VALUES (%s, %s, NOW())
            ON CONFLICT (request_signature) DO NOTHING
            """,
            (signature, _json.dumps(response)),
        )
    except psycopg2.Error as e:
        raise RuntimeError(
            f"IDEMPOTENCY INFRASTRUCTURE FAILURE: Cannot store idempotency cache: {type(e).__name__}: {e}. "
            f"Duplicate trade protection unavailable."
        ) from e


def handle(
    cur: cursor,
    path: str,
    method: str,
    params: dict[str, Any],
    body: dict[str, Any] | None = None,
    jwt_claims: dict[str, Any] | None = None,
    headers: dict[str, Any] | None = None,
) -> Any:
    """Handle /api/trades and /api/trades/* endpoints."""
    try:
        if path == "/api/trades/manual" and method == "POST":
            if not check_admin_access(jwt_claims):
                raise_api_error(403, "forbidden", "Admin access required")
            if not body:
                raise_api_error(400, "bad_request", "Request body is required")
            body_dict = cast(dict[str, Any], body)
            idempotency_key = headers.get("idempotency-key") if headers else None
            return _create_manual_trade(cur, body_dict, idempotency_key)
        if path == "/api/trades":
            if not check_admin_access(jwt_claims):
                raise_api_error(403, "forbidden", "Admin access required")
            limit = safe_limit(extract_param(params, "limit"), max_val=5000, default=500)
            offset = safe_offset(extract_param(params, "offset") or "0")
            status_filter = extract_param(params, "status")

            # Normalize status filter (centralized validation in data_queries)
            if status_filter:
                status_filter = status_filter.lower()

            try:
                cur.execute("SET LOCAL statement_timeout = '5000ms'")
                # Get trades from centralized data query (single source of truth)
                trades = get_trades_by_status(cur, status=status_filter, limit=limit, offset=offset)

                # Count total trades (use centralized counter)
                cur.execute("SET LOCAL statement_timeout = '3000ms'")
                total = count_trades_by_status(cur, status=status_filter)

                freshness = check_data_freshness(cur, "algo_trades", "created_at", warning_days=1)
                trades_result = list_response(
                    [safe_json_serialize(dict(t)) for t in trades],
                    total=total,
                    data_freshness=freshness,
                )
                is_valid, error_msg = ResponseValidator.validate_endpoint_response("trades", trades_result)
                if not is_valid:
                    # HIGH FIX: Return actual validation error, never fallback per GOVERNANCE.md
                    if error_msg:
                        logger.error(f"Endpoint response validation failed: {error_msg}")
                        return error_response(500, "response_validation_error", error_msg)
                    else:
                        logger.error("[CRITICAL] Response validation failed but error_msg is None. This is a bug.")
                        return error_response(500, "response_validation_error", "Response validation failed (internal error: no error message)")
                return trades_result
            except ValueError as e:
                return error_response(400, "bad_request", str(e))
        elif path == "/api/trades/summary":
            if not check_admin_access(jwt_claims):
                raise_api_error(403, "forbidden", "Admin access required")
            cur.execute("SET LOCAL statement_timeout = '4000ms'")
            cur.execute("""
                    SELECT
                        COUNT(*) as total_trades,
                        SUM(CASE WHEN exit_price > entry_price THEN 1 ELSE 0 END) as winning_trades,
                        COUNT(DISTINCT symbol) as unique_symbols,
                        SUM(CASE WHEN status = 'closed' THEN 1 ELSE 0 END) as closed_trades
                    FROM algo_trades
                """)
            summary = cur.fetchone()
            freshness = check_data_freshness(cur, "algo_trades", "created_at", warning_days=1)
            summary_result = safe_json_serialize(dict(summary)) if summary else {}
            summary_result["data_freshness"] = freshness
            is_valid, error_msg = ResponseValidator.validate_endpoint_response("trades", summary_result)
            if not is_valid:
                logger.error(f"Endpoint response validation failed: {error_msg}")
                if error_msg:
                    return error_response(500, "response_validation_error", error_msg)
                else:
                    logger.error("[CRITICAL] Trades summary validation failed but error_msg is None. Bug.")
                    return error_response(500, "response_validation_error", "Trades summary validation failed (internal error: no message)")
            return json_response(200, summary_result)
        raise_api_error(404, "not_found", f"Unknown trade endpoint: {path}")
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        logger.error(f"[TRADES] Unhandled error: {type(e).__name__}: {e}")
        raise_db_error(e, "handle trades")


def _create_manual_trade(cur: cursor, body: dict[str, Any], idempotency_key: str | None = None) -> Any:
    """POST /api/trades/manual — manually log a trade entry.

    If idempotency_key is provided, uses it to prevent duplicate requests.
    Returns cached response if the same request is retried within 24 hours.
    """
    try:
        signature = None
        if idempotency_key:
            signature = _compute_request_signature(idempotency_key, body)
            cache_check = _check_idempotency(cur, signature)
            # CRITICAL FIX: Explicit check for cached_response field — don't mask missing cache status with False
            has_cached = cache_check.get("cached_response")
            if has_cached is True:
                logger.info(f"Returning cached response for idempotent request: {idempotency_key}")
                return cache_check
            elif has_cached is None:
                logger.warning(
                    f"Idempotency check returned None for cached_response field — cache status unknown for {idempotency_key}"
                )

        try:
            req = ManualTradeRequest(**body)
        except ValidationError as e:
            errors = e.errors()
            if errors:
                error_detail = errors[0]
                field = error_detail.get("loc", ("unknown",))[0]
                msg = error_detail.get("msg", "Validation failed")
                raise_api_error(400, "bad_request", f"Invalid {field}: {msg}")
            raise_api_error(400, "bad_request", "Invalid request")

        symbol = req.symbol
        trade_type = req.trade_type.lower()
        quantity = req.quantity
        price = req.price
        execution_date = req.execution_date or date.today().isoformat()
        stop_loss = req.stop_loss_price

        # Business logic validation: stop loss must be within valid range
        if stop_loss is not None:
            if trade_type == "buy" and stop_loss >= price:
                raise_api_error(
                    400,
                    "bad_request",
                    f"For BUY trades, stop_loss_price ({stop_loss}) must be below entry_price ({price})",
                )
            elif trade_type == "sell" and stop_loss <= price:
                raise_api_error(
                    400,
                    "bad_request",
                    f"For SELL trades, stop_loss_price ({stop_loss}) must be above entry_price ({price})",
                )

        trade_id = f"MANUAL-{uuid.uuid4().hex[:12].upper()}"
        trade_date = date.fromisoformat(execution_date)
        status = "open" if trade_type == "buy" else "closed"

        cur.execute(
            """
            INSERT INTO algo_trades (
                trade_id, symbol, signal_date, trade_date, entry_price, entry_quantity,
                entry_reason, status, execution_mode, stop_loss_price, created_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            RETURNING id, trade_id
        """,
            (
                trade_id,
                symbol,
                trade_date,
                trade_date,
                price,
                quantity,
                f"manual_{trade_type}",
                status,
                "manual",
                float(stop_loss) if stop_loss else None,
            ),
        )
        row = cur.fetchone()
        manual_trade_response = {
            "success": True,
            "data": {"id": row["trade_id"], "trade_id": row["trade_id"]},
        }
        response = json_response(201, manual_trade_response)

        is_valid, error_msg = ResponseValidator.validate_endpoint_response("trades", manual_trade_response)
        if not is_valid:
            logger.error(f"Endpoint response validation failed: {error_msg}")
            if error_msg:
                return error_response(500, "response_validation_error", error_msg)
            else:
                logger.error("[CRITICAL] Trades stats validation failed but error_msg is None. Bug.")
                return error_response(500, "response_validation_error", "Trades stats validation failed (internal error: no message)")

        if signature:
            _store_idempotent_response(cur, signature, response)

        return response
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        code, error_type, message = handle_db_error(e, "create manual trade")
        return error_response(code, error_type, message)
