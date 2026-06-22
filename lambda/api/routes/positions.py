"""Route: positions - Handle position update and management endpoints."""

import logging
from typing import cast, Any

import psycopg2
import psycopg2.errors
from models.requests import PositionUpdateRequest
from psycopg2.extensions import cursor
from pydantic import ValidationError
from routes.utils import (
    error_response,
    handle_db_error,
    json_response,
    raise_api_error,
    raise_db_error,
)

from shared_contracts.response_validator import ResponseValidator
from utils.validation import CognitoValidator

logger = logging.getLogger(__name__)


def _check_admin_access(jwt_claims: dict | None) -> bool:
    """Check if user has admin access from verified JWT claims only."""
    result = CognitoValidator.validate_admin_access(jwt_claims)
    return bool(result)


def handle(
    cur: cursor,
    path: str,
    method: str,
    params: dict[str, Any],
    body: dict[str, Any] | None = None,
    jwt_claims: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Handle /api/position/* endpoints."""
    try:
        if path == "/api/position/update" and method in ("POST", "PUT"):
            if not _check_admin_access(jwt_claims):
                raise_api_error(403, "forbidden", "Admin access required")
            if not body:
                raise_api_error(400, "bad_request", "Request body is required")
            return _update_position(cur, body)

        raise_api_error(404, "not_found", f"No position handler for {path}")
    except Exception as e:
        logger.error(f"[POSITIONS] Unhandled error: {type(e).__name__}: {e}")
        raise_db_error(e, "handle positions")


def _update_position(cur, body: dict) -> dict[str, Any]:
    """POST/PUT /api/position/update - Update position parameters with validation.

    Validates:
    - Quantity must be positive
    - Stop loss price must be > 0 and make logical sense (not above entry for longs)
    - Target prices must be above entry price (for longs)
    - Targets should be in ascending order
    """
    try:
        req = PositionUpdateRequest(**body)
    except ValidationError as e:
        errors = e.errors()
        if errors:
            error_detail = errors[0]
            field = error_detail.get("loc", ("unknown",))[0]
            msg = error_detail.get("msg", "Validation failed")
            raise_api_error(400, "bad_request", f"Invalid {field}: {msg}")
        raise_api_error(400, "bad_request", "Invalid request")

    position_id = req.position_id

    try:
        req.validate_stop_loss_vs_entry()
        req.validate_targets_vs_entry()
        req.validate_targets_ordered()
    except ValueError as e:
        raise_api_error(400, "bad_request", str(e))

    try:
        cur.execute("SELECT id, symbol FROM algo_positions WHERE id = %s", (position_id,))
        position = cur.fetchone()
        if not position:
            raise_api_error(404, "not_found", f"Position {position_id} not found")

        symbol = position["symbol"] if hasattr(position, "__getitem__") else position[1]

        update_fields: list[str] = []
        update_args: list[Any] = []

        if req.quantity is not None:
            update_fields.append("quantity = %s")
            update_args.append(req.quantity)

        if req.stop_loss_price is not None:
            update_fields.append("stop_loss_price = %s")
            update_args.append(req.stop_loss_price)

        if req.target_1_price is not None:
            update_fields.append("target_1_price = %s")
            update_args.append(req.target_1_price)

        if req.target_2_price is not None:
            update_fields.append("target_2_price = %s")
            update_args.append(req.target_2_price)

        if req.target_3_price is not None:
            update_fields.append("target_3_price = %s")
            update_args.append(req.target_3_price)

        if not update_fields:
            return cast(
                dict[str, Any],
                json_response(
                    200,
                    {
                        "status": "no_changes",
                        "message": "No valid fields to update",
                        "position_id": position_id,
                    },
                ),
            )

        update_sql = ", ".join(update_fields)
        update_args.append(position_id)

        cur.execute(
            f"UPDATE algo_positions SET {update_sql}, updated_at = NOW() WHERE id = %s",
            update_args,
        )

        result = {
            "status": "success",
            "message": f"Updated position {position_id} ({symbol})",
            "position_id": position_id,
            "symbol": symbol,
            "updates": {
                "quantity": req.quantity,
                "stop_loss_price": req.stop_loss_price,
                "target_1_price": req.target_1_price,
                "target_2_price": req.target_2_price,
                "target_3_price": req.target_3_price,
            },
        }
        is_valid, error_msg = ResponseValidator.validate_endpoint_response("pos", result)
        if not is_valid:
            logger.error(f"Endpoint response validation failed: {error_msg}")
            return cast(dict[str, Any], error_response(500, "response_validation_error", error_msg))
        return cast(dict[str, Any], json_response(200, result))

    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        code, error_type, message = handle_db_error(e, "update position")
        return cast(dict[str, Any], error_response(code, error_type, message))
