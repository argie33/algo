"""Regression tests for POST /api/position/update's stop-loss/quantity handling.

BUG FOUND (real-money-readiness audit): this endpoint wrote stop_loss_price - the FROZEN,
entry-time reference column - instead of current_stop_price, the live/working stop every
real exit-trigger check actually reads (position_monitor.py's own 2026-08-03 fix: the
STOP_LOSS_HIT/trailing-stop comparison reads current_stop_price, never stop_loss_price).
An admin's stop-loss correction via this endpoint returned "200 success" but never moved
any price real exit logic would act on.

Separately, `quantity` was written to algo_positions.quantity only - but
position_sync.py's sync_positions_from_trades() (runs before every orchestrator
invocation) unconditionally recomputes that same column as SUM(algo_trades.quantity), so
an admin's quantity correction was silently reverted within one cycle. Fixed by also
correcting algo_trades.quantity for the single-leg case, and rejecting the edit outright
for a pyramided (2+ leg) position rather than accepting an edit with no safe per-leg
attribution.

'lambda' is a Python keyword, so the module under test is loaded via importlib rather
than a normal `from lambda...` import.
"""

import importlib
from unittest.mock import MagicMock

positions_module = importlib.import_module("lambda.api.routes.positions")


def _mock_cursor(position_row: dict) -> MagicMock:
    cur = MagicMock()
    cur.fetchone.return_value = position_row
    cur.rowcount = 1
    return cur


def _algo_positions_update_call(cur: MagicMock):
    for call in cur.execute.call_args_list:
        if call.args and "UPDATE algo_positions" in call.args[0]:
            return call
    return None


def _algo_trades_update_calls(cur: MagicMock):
    return [call for call in cur.execute.call_args_list if call.args and "UPDATE algo_trades" in call.args[0]]


def test_stop_loss_edit_writes_current_stop_price_not_stop_loss_price():
    cur = _mock_cursor({"id": 42, "symbol": "AAPL", "entry_price": 150.0, "trade_ids_arr": None})
    body = {"position_id": 42, "stop_loss_price": 145.0}

    response = positions_module._update_position(cur, body)

    assert response.get("statusCode") != 400, response
    call = _algo_positions_update_call(cur)
    assert call is not None
    sql = call.args[0]
    assert "current_stop_price = %s" in sql
    assert "stop_loss_price = %s" not in sql


def test_quantity_edit_on_single_leg_position_also_updates_algo_trades():
    cur = _mock_cursor({"id": 42, "symbol": "AAPL", "entry_price": 150.0, "trade_ids_arr": [101]})
    body = {"position_id": 42, "quantity": 25}

    response = positions_module._update_position(cur, body)

    assert response.get("statusCode") != 400, response
    trades_calls = _algo_trades_update_calls(cur)
    assert len(trades_calls) == 1
    sql, params = trades_calls[0].args
    assert "quantity = %s" in sql
    assert params == (25, 101)


def test_quantity_edit_on_pyramided_position_is_rejected_not_silently_reverted():
    """No safe per-leg attribution for a manual quantity correction across 2+ legs -
    must reject loudly rather than accept an edit position_sync will silently wipe."""
    cur = _mock_cursor({"id": 42, "symbol": "AAPL", "entry_price": 150.0, "trade_ids_arr": [101, 102]})
    body = {"position_id": 42, "quantity": 25}

    response = positions_module._update_position(cur, body)

    assert response.get("statusCode") == 400
    assert not _algo_trades_update_calls(cur)
    assert _algo_positions_update_call(cur) is None


def test_missing_trade_ids_arr_does_not_crash_stop_only_edit():
    """A row dict without the trade_ids_arr key at all (defensive - real production always
    selects it) must not raise; treated as unknown linkage, same as None."""
    cur = _mock_cursor({"id": 42, "symbol": "AAPL", "entry_price": 150.0})
    body = {"position_id": 42, "stop_loss_price": 145.0}

    response = positions_module._update_position(cur, body)

    assert response.get("statusCode") != 400, response


def test_response_includes_broker_sync_warning_when_stop_or_quantity_changed():
    cur = _mock_cursor({"id": 42, "symbol": "AAPL", "entry_price": 150.0, "trade_ids_arr": [101]})
    body = {"position_id": 42, "stop_loss_price": 145.0}

    response = positions_module._update_position(cur, body)

    assert response.get("statusCode") == 200, response
    assert response["data"].get("warnings"), "expected a warning about the broker order not being resynced"


def test_response_has_no_warning_when_only_targets_changed():
    """Target-only edits don't touch the broker-relevant fields - no warning needed."""
    cur = _mock_cursor({"id": 42, "symbol": "AAPL", "entry_price": 150.0, "trade_ids_arr": [101]})
    body = {"position_id": 42, "target_1_price": 160.0}

    response = positions_module._update_position(cur, body)

    assert response.get("statusCode") == 200, response
    assert response["data"].get("warnings") == []


def test_real_field_update_no_longer_500s_from_the_wrong_dashboard_contract():
    """BUG FOUND (real-money-readiness audit): _update_position used to run its result
    through ResponseValidator.validate_endpoint_response("pos", result) - but "pos" in
    DASHBOARD_ENDPOINTS is the GET /api/algo/positions LIST contract (requires an "items"
    list field), a completely different response shape. Every real field update (never
    has "items") failed that check and returned a 500 "response_validation_error" -
    meaning this admin endpoint had never actually returned success for a real change,
    only for the "no valid fields to update" no-op path (which returns before reaching
    that call). Confirmed by running this exact scenario against the pre-fix source."""
    cur = _mock_cursor({"id": 42, "symbol": "AAPL", "entry_price": 150.0, "trade_ids_arr": [101]})
    body = {"position_id": 42, "stop_loss_price": 145.0}

    response = positions_module._update_position(cur, body)

    assert response.get("statusCode") == 200, (
        f"a real field update must return 200, not a validate_endpoint_response 500: {response}"
    )


def test_response_validator_no_longer_imported():
    """The whole ResponseValidator call was validating against the wrong contract and has
    been removed entirely - it never belonged in a POST action-confirmation response."""
    assert not hasattr(positions_module, "ResponseValidator")
