"""Regression test: MarketEventHandler.check_single_stock_halt and check_delisting made
exactly one attempt each - same bug class as order_manager.py/position_monitor.py/
exit_engine.py's retry fixes. Both are real pre-trade gates ("cannot trade without halt
status verification" / "cannot trade without delisting verification"), so a transient
429/503 used to block real entries for no real reason instead of being retried.

Fixed by giving both the same up-to-3-attempt retry loop, retrying only on 429/503.

Also covers a second, narrower gap found the same day: the first retry loop only
inspected `response.status_code`, so a `requests.Timeout`/`ConnectionError` raised by
requests.get() itself (no status code exists yet) escaped the loop on the very first
attempt with zero retries - the same "one attempt only" bug for network-level failures
that the loop had just fixed for HTTP-level ones.
"""

import requests
from unittest.mock import MagicMock, patch

from algo.infrastructure.market_events import MarketEventHandler


def _handler():
    with (
        patch("algo.infrastructure.market_events.get_credential_manager") as mock_cred_manager,
        patch("algo.infrastructure.market_events.get_alpaca_base_url", return_value="https://api.alpaca.markets"),
    ):
        mock_cm = MagicMock()
        mock_cm.get_alpaca_credentials.return_value = {"key": "key", "secret": "secret"}
        mock_cred_manager.return_value = mock_cm
        return MarketEventHandler({"execution_mode": "paper"})


def _ok_asset_response(status="ACTIVE", tradable=True):
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"status": status, "tradable": tradable}
    return resp


class TestCheckSingleStockHaltRetriesTransientErrors:
    def test_429_then_success_retries_and_returns_result(self):
        handler = _handler()
        rate_limited = MagicMock(status_code=429, text="rate limited")

        with (
            patch(
                "algo.infrastructure.market_events.requests.get",
                side_effect=[rate_limited, _ok_asset_response()],
            ),
            patch("algo.infrastructure.market_events.get_api_timeout", return_value=10),
            patch("algo.infrastructure.market_events.time.sleep") as mock_sleep,
        ):
            result = handler.check_single_stock_halt("AAPL")

        assert result is not None
        assert result["halted"] is False
        mock_sleep.assert_called_once()

    def test_503_exhausts_retries_then_raises(self):
        handler = _handler()
        unavailable = MagicMock(status_code=503, text="service unavailable")

        with (
            patch(
                "algo.infrastructure.market_events.requests.get", return_value=unavailable
            ) as mock_get,
            patch("algo.infrastructure.market_events.get_api_timeout", return_value=10),
            patch("algo.infrastructure.market_events.time.sleep"),
        ):
            result = handler.check_single_stock_halt("AAPL")

        assert result is not None
        assert result.get("error") is not None
        assert mock_get.call_count == 3

    def test_timeout_then_success_retries_and_returns_result(self):
        handler = _handler()

        with (
            patch(
                "algo.infrastructure.market_events.requests.get",
                side_effect=[requests.Timeout("connection timed out"), _ok_asset_response()],
            ),
            patch("algo.infrastructure.market_events.get_api_timeout", return_value=10),
            patch("algo.infrastructure.market_events.time.sleep") as mock_sleep,
        ):
            result = handler.check_single_stock_halt("AAPL")

        assert result is not None
        assert result["halted"] is False
        mock_sleep.assert_called_once()

    def test_connection_error_exhausts_retries_then_returns_error(self):
        handler = _handler()

        with (
            patch(
                "algo.infrastructure.market_events.requests.get",
                side_effect=requests.ConnectionError("connection reset"),
            ) as mock_get,
            patch("algo.infrastructure.market_events.get_api_timeout", return_value=10),
            patch("algo.infrastructure.market_events.time.sleep"),
        ):
            result = handler.check_single_stock_halt("AAPL")

        assert result is not None
        assert result.get("error") is not None
        assert mock_get.call_count == 3


class TestCheckDelistingRetriesTransientErrors:
    def test_429_then_success_retries_and_returns_result(self):
        handler = _handler()
        rate_limited = MagicMock(status_code=429, text="rate limited")

        with (
            patch(
                "algo.infrastructure.market_events.requests.get",
                side_effect=[rate_limited, _ok_asset_response()],
            ),
            patch("algo.infrastructure.market_events.get_api_timeout", return_value=10),
            patch("algo.infrastructure.market_events.time.sleep") as mock_sleep,
        ):
            result = handler.check_delisting("AAPL")

        assert result is None  # active, not delisted
        mock_sleep.assert_called_once()

    def test_503_exhausts_retries_then_raises(self):
        handler = _handler()
        unavailable = MagicMock(status_code=503, text="service unavailable")

        with (
            patch(
                "algo.infrastructure.market_events.requests.get", return_value=unavailable
            ) as mock_get,
            patch("algo.infrastructure.market_events.get_api_timeout", return_value=10),
            patch("algo.infrastructure.market_events.time.sleep"),
        ):
            result = handler.check_delisting("AAPL")

        assert result is not None
        assert result.get("error") is not None
        assert mock_get.call_count == 3

    def test_timeout_then_success_retries_and_returns_result(self):
        handler = _handler()

        with (
            patch(
                "algo.infrastructure.market_events.requests.get",
                side_effect=[requests.Timeout("connection timed out"), _ok_asset_response()],
            ),
            patch("algo.infrastructure.market_events.get_api_timeout", return_value=10),
            patch("algo.infrastructure.market_events.time.sleep") as mock_sleep,
        ):
            result = handler.check_delisting("AAPL")

        assert result is None  # active, not delisted
        mock_sleep.assert_called_once()

    def test_connection_error_exhausts_retries_then_returns_error(self):
        handler = _handler()

        with (
            patch(
                "algo.infrastructure.market_events.requests.get",
                side_effect=requests.ConnectionError("connection reset"),
            ) as mock_get,
            patch("algo.infrastructure.market_events.get_api_timeout", return_value=10),
            patch("algo.infrastructure.market_events.time.sleep"),
        ):
            result = handler.check_delisting("AAPL")

        assert result is not None
        assert result.get("error") is not None
        assert mock_get.call_count == 3


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
