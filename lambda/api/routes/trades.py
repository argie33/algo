"""Route: trades"""

import hashlib
import json as _json
import logging
import os
import uuid
from datetime import date

import psycopg2
import psycopg2.errors
import psycopg2.extras
import psycopg2.sql
from models.requests import ManualTradeRequest
from pydantic import ValidationError
from routes.utils import (
    check_data_freshness,
    error_response,
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

from utils.validation import CognitoValidator


logger = logging.getLogger(__name__)


def _check_admin_access(jwt_claims: dict | None) -> bool:
    return CognitoValidator.validate_admin_access(jwt_claims)


def _compute_request_signature(idempotency_key: str, body: dict) -> str:
    """Compute a hash of the idempotency key and request body.

    Returns a deterministic signature to detect duplicate requests.
    """
    content = _json.dumps({"key": idempotency_key, "body": body}, sort_keys=True)
    return hashlib.sha256(content.encode()).hexdigest()


def _check_idempotency(cur, signature: str) -> dict | None:
    """Check if this request signature has been processed before.

    Returns the cached response if found, None otherwise.
    """
    try:
        cur.execute(
            """
            SELECT response_data FROM api_idempotency_cache
            WHERE request_signature = %s AND created_at > NOW() - INTERVAL '24 hours'
            LIMIT 1
            """,
            (signature,),
        )
        row = cur.fetchone()
        if row:
            return _json.loads(row[0])
        return None
    except (psycopg2.Error, _json.JSONDecodeError) as e:
        logger.warning(f"Idempotency check failed: {e}")
        return None


def _store_idempotent_response(cur, signature: str, response: dict) -> None:
    """Cache the response for this idempotent request signature."""
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
        logger.warning(f"Failed to cache idempotent response: {e}")


def handle(
    cur,
    path: str,
    method: str,
    params: dict,
    body: dict | None = None,
    jwt_claims: dict | None = None,
    headers: dict | None = None,
) -> dict:
    """Handle /api/trades and /api/trades/* endpoints."""
    try:
        if path == "/api/trades/manual" and method == "POST":
            if os.environ.get("DEV_BYPASS_AUTH") != "true" and not _check_admin_access(jwt_claims):
                raise_api_error(403, "forbidden", "Admin access required")
            if not body:
                raise_api_error(400, "bad_request", "Request body is required")
            idempotency_key = headers.get("idempotency-key") if headers else None
            return _create_manual_trade(cur, body, idempotency_key)
        if path == "/api/trades":
            if os.environ.get("DEV_BYPASS_AUTH") != "true" and not _check_admin_access(jwt_claims):
                raise_api_error(403, "forbidden", "Admin access required")
            limit_str = params.get("limit", [None])[0] if params else None
            limit = safe_limit(limit_str or "500", max_val=5000)
            offset_str = params.get("offset", [None])[0] if params else None
            offset = safe_offset(offset_str or "0")
            status_filter = params.get("status", [None])[0] if params else None

            # SECURITY FIX: Validate status filter against whitelist (enum validation)
            valid_statuses = {
                "pending",
                "open",
                "closed",
                "filled",
                "cancelled",
                "rejected",
            }
            if status_filter:
                if status_filter.lower() not in valid_statuses:
                    return error_response(
                        400, "bad_request", f"Invalid status value: {status_filter}"
                    )
                status_filter = status_filter.lower()

            where_clauses = []
            where_args = []
            if status_filter:
                where_clauses.append("status = %s")
                where_args.append(status_filter)

            where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"
            query = f"""
                SELECT trade_id, symbol, signal_date, trade_date, entry_time,
                       entry_price, entry_quantity, entry_reason,
                       exit_price, exit_date, exit_reason,
                       stop_loss_price, status, profit_loss_dollars, profit_loss_pct,
                       execution_mode, created_at
                FROM algo_trades
                WHERE {where_sql}
                ORDER BY created_at DESC LIMIT %s OFFSET %s
            """
            query_args = where_args + [limit, offset]
            cur.execute("SET LOCAL statement_timeout = '5000ms'")
            cur.execute(query, query_args)
            trades = cur.fetchall()
            # Count total trades (use only where clause args, no limit/offset)
            count_query = f"SELECT COUNT(*) FROM algo_trades WHERE {where_sql}"
            count_args = where_args
            cur.execute("SET LOCAL statement_timeout = '3000ms'")
            cur.execute(count_query, count_args)
            count_row = cur.fetchone()
            total = count_row[0] if count_row and count_row[0] is not None else 0
            freshness = check_data_freshness(
                cur, "algo_trades", "created_at", warning_days=1
            )
            trades_result = list_response(
                [safe_json_serialize(dict(t)) for t in trades],
                total=total,
                data_freshness=freshness,
            )
            is_valid, error_msg = ResponseValidator.validate_endpoint_response("trades", trades_result)
            if not is_valid:
                logger.error(f"Endpoint response validation failed: {error_msg}")
                return error_response(500, "response_validation_error", error_msg)
            return trades_result
        elif path == "/api/trades/summary":
            if os.environ.get("DEV_BYPASS_AUTH") != "true" and not _check_admin_access(jwt_claims):
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
            freshness = check_data_freshness(
                cur, "algo_trades", "created_at", warning_days=1
            )
            summary_result = safe_json_serialize(dict(summary)) if summary else {}
            summary_result["data_freshness"] = freshness
            is_valid, error_msg = ResponseValidator.validate_endpoint_response("trades", summary_result)
            if not is_valid:
                logger.error(f"Endpoint response validation failed: {error_msg}")
                return error_response(500, "response_validation_error", error_msg)
            return json_response(200, summary_result)
        raise_api_error(404, "not_found", f"Unknown trade endpoint: {path}")
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        logger.error(f"[TRADES] Unhandled error: {type(e).__name__}: {e}")
        raise_db_error(e, "handle trades")


def _create_manual_trade(cur, body: dict, idempotency_key: str | None = None) -> dict:
    """POST /api/trades/manual — manually log a trade entry.

    If idempotency_key is provided, uses it to prevent duplicate requests.
    Returns cached response if the same request is retried within 24 hours.
    """
    try:
        signature = None
        if idempotency_key:
            signature = _compute_request_signature(idempotency_key, body)
            cached = _check_idempotency(cur, signature)
            if cached:
                logger.info(f"Returning cached response for idempotent request: {idempotency_key}")
                return cached

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
                    400, "bad_request",
                    f"For BUY trades, stop_loss_price ({stop_loss}) must be below entry_price ({price})"
                )
            elif trade_type == "sell" and stop_loss <= price:
                raise_api_error(
                    400, "bad_request",
                    f"For SELL trades, stop_loss_price ({stop_loss}) must be above entry_price ({price})"
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
            return error_response(500, "response_validation_error", error_msg)

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
