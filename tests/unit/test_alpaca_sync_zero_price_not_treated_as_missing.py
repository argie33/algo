"""Regression: `float(current_price) if current_price else None` (and the equivalent for
position_value) treated a legitimate current_price=0.0 as falsy, silently writing NULL to
current_price/position_value in algo_positions instead of 0.0 - the same falsy-vs-None
anti-pattern this codebase already identified and fixed elsewhere for financial fields (see
lambda/api/routes/algo_handlers/dashboard.py's "FIX: Use explicit None checks instead of falsy
checks (0.0 is a valid price)"), but left unfixed in the actual Alpaca position-sync path that
writes the canonical algo_positions record. Fixed by using `is not None` everywhere current_price
/position_value is converted before a DB write in alpaca_sync_manager.py.
"""

from unittest.mock import MagicMock, patch

from algo.infrastructure.alpaca_sync_manager import AlpacaSyncManager


def _make_manager():
    manager = object.__new__(AlpacaSyncManager)
    manager.config = {"execution_mode": "auto", "api_request_timeout_seconds": 10}
    manager._alpaca_key = "key"
    manager._alpaca_secret = "secret"
    manager._alpaca_base_url = "https://paper-api.alpaca.markets"
    manager.fetch_alpaca_account = MagicMock()
    return manager


def _mock_positions_response(positions):
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = positions
    return resp


def test_zero_current_price_is_written_as_zero_not_null():
    manager = _make_manager()
    manager._session = MagicMock()
    manager._session.get.return_value = _mock_positions_response(
        [{"symbol": "AAPL", "qty": "10", "avg_entry_price": "150.00", "current_price": 0.0}]
    )

    cur = MagicMock()
    cur.fetchone.return_value = (10.0,)  # prior DB quantity matches, no drift alert
    cur.rowcount = 1

    with patch("algo.reporting.notify"):
        manager._sync_alpaca_positions_impl(cur)

    update_call = next(c for c in cur.execute.call_args_list if "UPDATE algo_positions" in c.args[0])
    params = update_call.args[1]
    # params order: quantity, current_price, position_value, symbol
    assert params[1] == 0.0, f"current_price=0.0 must be written as 0.0, not NULL - got {params[1]!r}"
    assert params[2] == 0.0, f"position_value must be 0.0 (10 * 0.0), not NULL - got {params[2]!r}"
