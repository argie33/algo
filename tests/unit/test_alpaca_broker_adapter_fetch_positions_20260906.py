"""Regression tests for AlpacaBrokerAdapter.fetch_positions() (2026-09-06, real-money-
readiness audit): a live-broker position fetch added for algo/risk/intraday_risk_monitor.py,
which cannot use algo_positions.current_price/quantity - that column is only refreshed
once/day by Phase 3's EOD price_daily-based update, so intraday it can be hours stale,
exactly the kind of gap the intraday risk monitor exists to catch.
"""

from unittest.mock import MagicMock

import pytest

from algo.infrastructure.alpaca_broker_adapter import AlpacaBrokerAdapter


def _make_adapter():
    adapter = object.__new__(AlpacaBrokerAdapter)
    adapter.config = {"api_request_timeout_seconds": 10}
    adapter.alpaca_sync = MagicMock()
    adapter.alpaca_sync.alpaca_key = "key"
    adapter.alpaca_sync.alpaca_secret = "secret"
    adapter.alpaca_sync.alpaca_base_url = "https://paper-api.alpaca.markets"
    adapter._session = MagicMock()
    return adapter


def _positions_response(body):
    resp = MagicMock(status_code=200)
    resp.json.return_value = body
    return resp


class TestFetchPositions:
    def test_real_positions_parsed(self):
        adapter = _make_adapter()
        adapter._session.get.return_value = _positions_response(
            [
                {"symbol": "AAPL", "qty": "10", "market_value": "1750.50", "current_price": "175.05"},
                {"symbol": "MSFT", "qty": "-5", "market_value": "-2000.00", "current_price": "400.00"},
            ]
        )
        positions = adapter.fetch_positions()
        assert positions == [
            {"symbol": "AAPL", "qty": 10.0, "market_value": 1750.50, "current_price": 175.05},
            {"symbol": "MSFT", "qty": -5.0, "market_value": -2000.00, "current_price": 400.00},
        ]

    def test_empty_positions(self):
        adapter = _make_adapter()
        adapter._session.get.return_value = _positions_response([])
        assert adapter.fetch_positions() == []

    def test_non_finite_value_raises(self):
        adapter = _make_adapter()
        adapter._session.get.return_value = _positions_response(
            [{"symbol": "AAPL", "qty": "10", "market_value": "nan", "current_price": "175.05"}]
        )
        with pytest.raises(ValueError, match="non-finite"):
            adapter.fetch_positions()

    def test_missing_field_raises(self):
        adapter = _make_adapter()
        adapter._session.get.return_value = _positions_response([{"symbol": "AAPL", "qty": "10"}])
        with pytest.raises(ValueError, match="missing required field"):
            adapter.fetch_positions()

    def test_non_200_raises(self):
        adapter = _make_adapter()
        resp = MagicMock(status_code=500, text="Internal Server Error")
        adapter._session.get.return_value = resp
        with pytest.raises(ValueError, match="HTTP 500"):
            adapter.fetch_positions()

    def test_non_list_response_raises(self):
        adapter = _make_adapter()
        adapter._session.get.return_value = _positions_response({"error": "not a list"})
        with pytest.raises(ValueError, match="non-list"):
            adapter.fetch_positions()

    def test_missing_credentials_raises(self):
        adapter = _make_adapter()
        adapter.alpaca_sync.alpaca_key = None
        with pytest.raises(RuntimeError, match="credentials not available"):
            adapter.fetch_positions()
