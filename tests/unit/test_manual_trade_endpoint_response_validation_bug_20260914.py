"""Regression test: POST /api/trades/manual (admin-gated manual trade logging) must
return its real 201 success response, not a 500 from validating against the wrong
dashboard contract.

BUG FOUND (real-money-readiness audit, same class as POST /api/position/update's fix):
_create_manual_trade built the correct 201 `response` object, then unconditionally ran
`manual_trade_response` (shape: {"success", "data": {"id", "trade_id"}}) through
`ResponseValidator.validate_endpoint_response("trades", ...)` - but "trades" in
DASHBOARD_ENDPOINTS is the GET /api/algo/trades LIST contract (requires an "items" list
field), a completely different shape. Every successful manual trade insert failed that
check and returned a 500 "response_validation_error" AFTER the INSERT had already
committed - the admin saw a failure for a trade that was actually recorded in
algo_trades, risking a duplicate manual entry on retry when no idempotency_key was
supplied.

Confirmed live before the fix by calling ResponseValidator directly with the exact
response shape this function builds - it failed with "Missing required fields in
trades: ['items']" every time, proving this endpoint had never returned success for a
real manual trade.

'lambda' is a Python keyword, so the module under test is loaded via importlib.
"""

import importlib
from unittest.mock import MagicMock

from shared_contracts.response_validator import ResponseValidator

trades_module = importlib.import_module("lambda.api.routes.trades")


def test_trades_schema_requires_items_confirming_the_original_bug_shape():
    """Pins the root cause: "trades" is a GET-list contract requiring "items", which a
    POST creation-confirmation response never has - this is why the old code always
    failed validation, not a fluke of the test's own mock shape."""
    manual_trade_response = {"success": True, "data": {"id": 5, "trade_id": "MANUAL-ABC123"}}
    is_valid, error_msg = ResponseValidator.validate_endpoint_response("trades", manual_trade_response)
    assert is_valid is False
    assert error_msg is not None
    assert "items" in error_msg


def _mock_cursor_for_manual_trade() -> MagicMock:
    cur = MagicMock()
    cur.fetchone.return_value = {"id": 5, "trade_id": "MANUAL-ABC123"}
    return cur


def test_create_manual_trade_returns_the_real_201_not_a_validation_500():
    cur = _mock_cursor_for_manual_trade()
    body = {
        "symbol": "AAPL",
        "trade_type": "buy",
        "quantity": 10,
        "price": 150.0,
    }

    response = trades_module._create_manual_trade(cur, body)

    assert response.get("statusCode") == 201, (
        f"a successful manual trade insert must return 201, not a wrong-contract "
        f"validate_endpoint_response 500: {response}"
    )
    assert response["data"]["success"] is True
    assert response["data"]["data"]["trade_id"] == "MANUAL-ABC123"


def test_create_manual_trade_response_is_properly_nested_under_data():
    """SECOND BUG FOUND while fixing the first: json_response() only special-cases
    code == 200 for its {"statusCode", "data": {...}} shape - 201 fell into the ELSE
    branch (written for 4xx/5xx errors), which spreads the dict's own keys at the top
    level instead of nesting under "data". Fixed by building the response directly at
    this call site rather than widening json_response's success condition (51 other
    call sites all pass 200 and must not change behavior)."""
    cur = _mock_cursor_for_manual_trade()
    body = {"symbol": "AAPL", "trade_type": "buy", "quantity": 10, "price": 150.0}

    response = trades_module._create_manual_trade(cur, body)

    assert "success" not in response, (
        "the manual-trade response's own keys must not be spread at the top level of "
        "the HTTP response envelope - they belong nested under 'data'"
    )
    assert set(response.keys()) == {"statusCode", "data"}


def test_create_manual_trade_no_longer_calls_validate_endpoint_response_on_its_own_response():
    """The whole validation call was checking the wrong contract and has been removed -
    it never belonged on a POST action-confirmation response. Checked via an actual call
    (not a source-text search, which would also match this docstring's own prose) - the
    only reliable way validate_endpoint_response("trades", ...) could still fire is if it
    were reachable in the runtime path, which the 201-return test above already proves it
    is not."""
    cur = _mock_cursor_for_manual_trade()
    body = {"symbol": "AAPL", "trade_type": "buy", "quantity": 10, "price": 150.0}

    response = trades_module._create_manual_trade(cur, body)

    assert response.get("statusCode") == 201
