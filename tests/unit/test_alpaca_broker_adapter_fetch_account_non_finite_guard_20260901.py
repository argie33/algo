"""Regression test: AlpacaBrokerAdapter.fetch_account() must reject a non-finite (NaN/
Infinity) cash/equity/portfolio_value/buying_power value instead of passing it through as
real broker truth.

None of these four numeric fields were previously checked for NaN/Infinity before being
returned. A malformed Alpaca response (network/proxy corruption, or a numeric string like
"nan"/"inf" that float() silently accepts) would otherwise flow into every caller as a
normal-looking float - this is the single choke point every caller of live account data
goes through (position_sizer.py, reconciliation.py, phase2_circuit_breakers.py), so it
must guard here rather than relying on every current and future caller re-deriving the
same protection independently.
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


def _account_response(**overrides):
    resp = MagicMock(status_code=200)
    body = {
        "cash": "1000.00",
        "equity": "5000.00",
        "portfolio_value": "5000.00",
        "buying_power": "10000.00",
        "trading_blocked": False,
        "account_blocked": False,
        "pattern_day_trader": False,
        "daytrade_count": 0,
    }
    body.update(overrides)
    resp.json.return_value = body
    return resp


class TestFetchAccountNonFiniteGuard:
    @pytest.mark.parametrize("field", ["cash", "equity", "portfolio_value", "buying_power"])
    @pytest.mark.parametrize("bad_value", ["nan", "inf", "-inf"])
    def test_non_finite_field_raises(self, field, bad_value):
        adapter = _make_adapter()
        adapter._session.get.return_value = _account_response(**{field: bad_value})

        with pytest.raises(ValueError, match="non-finite"):
            adapter.fetch_account()

    def test_all_finite_fields_succeed(self):
        adapter = _make_adapter()
        adapter._session.get.return_value = _account_response()

        result = adapter.fetch_account()

        assert result["cash"] == 1000.0
        assert result["equity"] == 5000.0
        assert result["portfolio_value"] == 5000.0
        assert result["buying_power"] == 10000.0
