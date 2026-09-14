"""Route: positions - Handle position update and management endpoints."""

from __future__ import annotations

import logging
from typing import Any

import psycopg2
import psycopg2.errors
from auth_utils import check_admin_access
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

logger = logging.getLogger(__name__)


def handle(
    cur: cursor,
    path: str,
    method: str,
    params: dict[str, Any],
    body: dict[str, Any] | None = None,
    jwt_claims: dict[str, Any] | None = None,
) -> Any:
    """Handle /api/position/* endpoints."""
    try:
        if path == "/api/position/update" and method in ("POST", "PUT"):
            if not check_admin_access(jwt_claims):
                raise_api_error(403, "forbidden", "Admin access required")
            if body is None:
                raise_api_error(400, "bad_request", "Request body is required")
            assert body is not None
            return _update_position(cur, body)

        raise_api_error(404, "not_found", f"No position handler for {path}")
    except Exception as e:
        logger.error(f"[POSITIONS] Unhandled error: {type(e).__name__}: {e}")
        raise_db_error(e, "handle positions")


def _update_position(cur: cursor, body: dict[str, Any]) -> Any:
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
        cur.execute("SELECT id, symbol, entry_price, trade_ids_arr FROM algo_positions WHERE id = %s", (position_id,))
        position = cur.fetchone()
        if not position:
            raise_api_error(404, "not_found", f"Position {position_id} not found")

        symbol = position["symbol"] if hasattr(position, "__getitem__") else position[1]
        db_entry_price = position["entry_price"] if hasattr(position, "__getitem__") else position[2]
        # .get() (not [...]) for the dict-like case - unlike symbol/entry_price above, older
        # test doubles/callers may hand back a row dict without this column; treating that as
        # "no trade linkage known yet" (None) rather than raising is the same defensive
        # posture the rest of this function already applies to optional fields.
        if hasattr(position, "get"):
            trade_ids_arr = position.get("trade_ids_arr")
        else:
            trade_ids_arr = position[3]

        # SECURITY/DATA-INTEGRITY FIX: the cross-field validators below silently no-op
        # when entry_price/position_type are None, and both were previously optional
        # client-supplied fields never cross-checked against the real position. That let
        # a caller omit them (or the frontend simply never send them) and push a stop
        # loss above entry or a target below entry with zero server-side guardrail,
        # despite the DB already holding the real entry_price right here. This is a
        # long-only algo (only buy_signal_generator.py exists, no short-entry path), so
        # position_type is always "buy" for real positions - override any client-supplied
        # entry_price/position_type with the authoritative DB value before validating.
        if db_entry_price is not None:
            req.entry_price = float(db_entry_price)
        req.position_type = "buy"

        try:
            req.validate_stop_loss_vs_entry()
            req.validate_targets_vs_entry()
            req.validate_targets_ordered()
        except ValueError as e:
            raise_api_error(400, "bad_request", str(e))

        update_fields: list[str] = []
        update_args: list[Any] = []

        # FIX (real-money-readiness audit): quantity was written to algo_positions.quantity
        # only - but algo_positions.py's own sync_positions_from_trades() (runs before EVERY
        # orchestrator invocation, multiple times a day) unconditionally recomputes that same
        # column as SUM(algo_trades.quantity) across every open trade on the position. An
        # admin's quantity correction here was silently reverted within one cycle, with the
        # caller having already received a "status": "success" response. For the common
        # single-leg case, also correct the underlying algo_trades.quantity so the value
        # actually survives the next sync. A pyramided (2+ leg) position has no established
        # per-leg attribution for a manual quantity correction (the same open question fix #8
        # this session left for multi-leg partial exits) - reject rather than accept an edit
        # that would silently vanish, or worse, get attributed to the wrong leg.
        if req.quantity is not None:
            if trade_ids_arr and len(trade_ids_arr) > 1:
                raise_api_error(
                    400,
                    "bad_request",
                    f"Position {position_id} has {len(trade_ids_arr)} pyramid legs - a manual "
                    f"quantity correction has no safe per-leg attribution and would be silently "
                    f"reverted by the next position-sync cycle regardless. Correct the specific "
                    f"leg's algo_trades.quantity directly instead.",
                )
            update_fields.append("quantity = %s")
            update_args.append(req.quantity)
            if trade_ids_arr:
                cur.execute(
                    "UPDATE algo_trades SET quantity = %s WHERE trade_id = %s",
                    (req.quantity, trade_ids_arr[0]),
                )

        # FIX (real-money-readiness audit): this wrote stop_loss_price - the FROZEN,
        # entry-time reference column - not current_stop_price, the live/working stop every
        # real exit-trigger check actually reads (position_monitor.py's own 2026-08-03 fix
        # comment: "_evaluate_position...used as active_stop for every STOP_LOSS_HIT/
        # trailing-stop decision" reads current_stop_price, never stop_loss_price). Every
        # other stop-adjustment code path in this codebase (_raise_stop_only, Phase 6's
        # tighten_stop, resize_standalone_stop_after_partial_exit) writes current_stop_price
        # exclusively - an admin's stop-loss correction via this endpoint returned a "200
        # success" but never actually moved the price any real exit logic would act on.
        if req.stop_loss_price is not None:
            update_fields.append("current_stop_price = %s")
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
            return json_response(
                200,
                {
                    "status": "no_changes",
                    "message": "No valid fields to update",
                    "position_id": position_id,
                },
            )

        update_sql = ", ".join(update_fields)
        update_args.append(position_id)

        cur.execute(
            f"UPDATE algo_positions SET {update_sql}, updated_at = NOW() WHERE id = %s",
            update_args,
        )
        # The existence check above (SELECT ... WHERE id = %s) narrows the race but doesn't
        # close it - the position can still be closed/deleted between that SELECT and this
        # UPDATE (e.g. the exit engine or position monitor racing this admin edit). Without
        # checking rowcount, that race silently reports "status": "success" with the request
        # body's intended values even though nothing in the database actually changed.
        if cur.rowcount == 0:
            raise_api_error(
                404, "not_found", f"Position {position_id} was not found at update time (may have just closed)"
            )

        # Neither field syncs to the broker - the resting bracket/standalone stop order (if
        # any) keeps whatever price/quantity it already had until the next Phase 9
        # reconciliation cycle or a real trailing-stop raise resyncs it. Surfacing this
        # explicitly rather than letting a "200 success" imply the broker-side order also
        # changed - this endpoint corrects OUR records, it does not itself talk to Alpaca.
        warnings = []
        if req.stop_loss_price is not None or req.quantity is not None:
            warnings.append(
                "This update changes algo_positions/algo_trades only - it does NOT resync "
                "the broker's resting stop-loss/bracket order. If one exists, it still "
                "reflects the pre-update price/quantity until the next reconciliation cycle "
                "or trailing-stop raise."
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
            "warnings": warnings,
        }
        # FIX (real-money-readiness audit): this used to run this dict through
        # ResponseValidator.validate_endpoint_response("pos", result) - but "pos" in
        # DASHBOARD_ENDPOINTS is the GET /api/algo/positions LIST contract (requires an
        # "items" list field), not this POST update-confirmation response. Every real
        # update (this dict never has "items") failed that check and returned a 500
        # "response_validation_error" - meaning this admin tool has never actually
        # returned success for a real field change, only for the "no valid fields to
        # update" no-op path above (which returns early, before reaching this call).
        # ResponseValidator exists to validate GET responses the dashboard renders against
        # a published read contract; a POST action-confirmation has no such contract to
        # check against, so this call never belonged here.
        return json_response(200, result)

    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        code, error_type, message = handle_db_error(e, "update position")
        return error_response(code, error_type, message)
