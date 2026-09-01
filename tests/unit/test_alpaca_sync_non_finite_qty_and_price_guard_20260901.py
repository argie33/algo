"""Regression test: AlpacaSyncManager must not write a NaN/Infinity qty or current_price
into algo_positions or algo_untracked_positions.

`qty_float <= 0` (the existing short/zero-position guard) is a no-op for NaN - every
comparison against NaN is False in IEEE 754/Python - so a malformed Alpaca response
(network/proxy corruption, or a numeric string like "nan"/"inf" that float() silently
accepts) would fall through and write a non-finite quantity straight into
algo_positions.quantity. PostgreSQL NUMERIC legally accepts NaN, so this would persist
silently with no exception and no downstream validation catching it. Same NaN/Infinity
guard convention this codebase applies everywhere else price-derived data crosses a trust
boundary (see e.g. capital_routing.py's math.isnan/isinf checks, MEMORY.md's blanket rule).
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


class TestNonFiniteQuantityGuard:
    def test_nan_qty_is_skipped_not_written(self):
        manager = _make_manager()
        manager._session = MagicMock()
        manager._session.get.return_value = _mock_positions_response(
            [{"symbol": "AAPL", "qty": "nan", "avg_entry_price": "150.00", "current_price": 100.0}]
        )

        cur = MagicMock()
        cur.fetchone.return_value = None
        cur.rowcount = 0

        with patch("algo.reporting.notify"):
            manager._sync_alpaca_positions_impl(cur)

        update_calls = [c for c in cur.execute.call_args_list if "UPDATE algo_positions" in c.args[0]]
        assert not update_calls, "a NaN qty must never reach the algo_positions UPDATE"

    def test_infinite_qty_is_skipped_not_written(self):
        manager = _make_manager()
        manager._session = MagicMock()
        manager._session.get.return_value = _mock_positions_response(
            [{"symbol": "AAPL", "qty": "inf", "avg_entry_price": "150.00", "current_price": 100.0}]
        )

        cur = MagicMock()
        cur.fetchone.return_value = None
        cur.rowcount = 0

        with patch("algo.reporting.notify"):
            manager._sync_alpaca_positions_impl(cur)

        update_calls = [c for c in cur.execute.call_args_list if "UPDATE algo_positions" in c.args[0]]
        assert not update_calls, "an infinite qty must never reach the algo_positions UPDATE"

    def test_nan_current_price_falls_back_to_none_not_written_as_nan(self):
        manager = _make_manager()
        manager._session = MagicMock()
        manager._session.get.return_value = _mock_positions_response(
            [{"symbol": "AAPL", "qty": "10", "avg_entry_price": "150.00", "current_price": "nan"}]
        )

        cur = MagicMock()
        cur.fetchone.return_value = (10.0,)
        cur.rowcount = 1

        with patch("algo.reporting.notify"):
            manager._sync_alpaca_positions_impl(cur)

        update_call = next(c for c in cur.execute.call_args_list if "UPDATE algo_positions" in c.args[0])
        params = update_call.args[1]
        # params order: quantity, current_price, position_value, symbol
        assert params[1] is None, f"a NaN current_price must be written as NULL, not NaN - got {params[1]!r}"
        assert params[2] is None, f"position_value derived from a NaN price must also be NULL - got {params[2]!r}"

    def test_valid_qty_and_price_still_write_normally(self):
        """Sanity check the guard doesn't reject legitimate data."""
        manager = _make_manager()
        manager._session = MagicMock()
        manager._session.get.return_value = _mock_positions_response(
            [{"symbol": "AAPL", "qty": "10", "avg_entry_price": "150.00", "current_price": 155.5}]
        )

        cur = MagicMock()
        cur.fetchone.return_value = (10.0,)
        cur.rowcount = 1

        with patch("algo.reporting.notify"):
            manager._sync_alpaca_positions_impl(cur)

        update_call = next(c for c in cur.execute.call_args_list if "UPDATE algo_positions" in c.args[0])
        params = update_call.args[1]
        assert params[0] == 10.0
        assert params[1] == 155.5
        assert params[2] == 1555.0
