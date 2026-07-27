"""Regression tests for POST /api/position/update's stop/target validation.

_update_position (lambda/api/routes/positions.py) already queries the real
position row from algo_positions (which has entry_price), but the cross-field
validators on PositionUpdateRequest (validate_stop_loss_vs_entry,
validate_targets_vs_entry, validate_targets_ordered) all silently no-op when
entry_price/position_type are None - and both were only ever populated from
optional client-supplied request fields, never from the DB row already fetched
in the same function. A caller that simply omitted entry_price/position_type
(or a frontend that never sends them) could push a stop loss above entry or a
target below entry with zero server-side guardrail, despite the real entry
price sitting right there in the query result. Fixed by overriding any
client-supplied entry_price/position_type with the authoritative DB value
(this is a long-only algo - only buy_signal_generator.py exists, no
short-entry path - so position_type is always "buy") before validating.

'lambda' is a Python keyword, so the module under test is loaded via
importlib rather than a normal `from lambda...` import.
"""

import importlib
from unittest.mock import MagicMock

positions_module = importlib.import_module("lambda.api.routes.positions")


def _mock_cursor(position_row: dict) -> MagicMock:
    cur = MagicMock()
    cur.fetchone.return_value = position_row
    cur.rowcount = 1
    return cur


def _has_update_call(cur: MagicMock) -> bool:
    return any("UPDATE algo_positions" in call.args[0] for call in cur.execute.call_args_list if call.args)


def test_stop_loss_above_entry_rejected_even_without_client_entry_price():
    """Client omits entry_price/position_type entirely - server must still
    reject a stop_loss above the real DB entry_price for a long position."""
    cur = _mock_cursor({"id": 42, "symbol": "AAPL", "entry_price": 150.0})
    body = {"position_id": 42, "stop_loss_price": 160.0}  # above entry - invalid for a long

    response = positions_module._update_position(cur, body)

    assert response.get("statusCode") == 400
    assert not _has_update_call(cur)  # rejected input must never reach the UPDATE


def test_target_below_entry_rejected_even_without_client_entry_price():
    """Same gap, target side: a target below the real entry price for a long
    position must be rejected even when the client never supplied entry_price."""
    cur = _mock_cursor({"id": 42, "symbol": "AAPL", "entry_price": 150.0})
    body = {"position_id": 42, "target_1_price": 140.0}  # below entry - invalid for a long

    response = positions_module._update_position(cur, body)

    assert response.get("statusCode") == 400
    assert not _has_update_call(cur)


def test_valid_stop_and_target_still_succeed():
    """Sanity check: a legitimate update (stop below entry, target above entry)
    must still succeed using the DB-sourced entry_price."""
    cur = _mock_cursor({"id": 42, "symbol": "AAPL", "entry_price": 150.0})
    body = {"position_id": 42, "stop_loss_price": 145.0, "target_1_price": 160.0}

    response = positions_module._update_position(cur, body)

    assert response.get("statusCode") != 400
    assert _has_update_call(cur)
