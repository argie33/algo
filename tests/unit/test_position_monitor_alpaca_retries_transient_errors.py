"""Regression test: PositionMonitor._cancel_on_alpaca (stale-order cleanup) and
_fetch_alpaca_qty (corporate-action detection) made exactly one attempt each - same bug class
as order_manager.py's send_bracket_order/cancel_bracket_orders fixes. A transient Alpaca
429/503 used to raise RuntimeError immediately, and since both call sites are fail-fast by
design (the whole point is "don't proceed on ambiguous broker state"), that RuntimeError
propagates straight up and aborts the entire cycle - a bigger blast radius than the
order_manager.py cases, which only affected one order.

Fixed by giving both the same up-to-3-attempt retry loop, retrying only on 429/503 and
request exceptions.
"""

from unittest.mock import MagicMock, patch

import requests

from algo.monitoring.position_monitor import PositionMonitor


def _config():
    return {"api_request_timeout_seconds": 10, "execution_mode": "paper"}


def _monitor():
    return PositionMonitor(config=_config())


class TestCancelOnAlpacaRetriesTransientErrors:
    def test_429_then_success_retries_and_succeeds(self):
        monitor = _monitor()
        rate_limited = MagicMock(status_code=429, text="rate limited")
        cancelled = MagicMock(status_code=204)

        with (
            patch(
                "algo.monitoring.position_monitor.get_alpaca_credentials",
                return_value={"key": "k", "secret": "s"},
            ),
            patch(
                "algo.monitoring.position_monitor.get_alpaca_base_url",
                return_value="https://paper-api.alpaca.markets",
            ),
            patch(
                "algo.monitoring.position_monitor.requests.delete",
                side_effect=[rate_limited, cancelled],
            ),
            patch("algo.monitoring.position_monitor.time.sleep") as mock_sleep,
        ):
            monitor._cancel_on_alpaca("trade-1")  # must not raise

        mock_sleep.assert_called_once()

    def test_503_exhausts_retries_then_raises(self):
        monitor = _monitor()
        unavailable = MagicMock(status_code=503, text="service unavailable")

        with (
            patch(
                "algo.monitoring.position_monitor.get_alpaca_credentials",
                return_value={"key": "k", "secret": "s"},
            ),
            patch(
                "algo.monitoring.position_monitor.get_alpaca_base_url",
                return_value="https://paper-api.alpaca.markets",
            ),
            patch("algo.monitoring.position_monitor.requests.delete", return_value=unavailable) as mock_delete,
            patch("algo.monitoring.position_monitor.time.sleep"),
        ):
            try:
                monitor._cancel_on_alpaca("trade-1")
                raise AssertionError("expected RuntimeError")
            except RuntimeError as e:
                assert "503" in str(e)

        assert mock_delete.call_count == 3


class TestFetchAlpacaQtyRetriesTransientErrors:
    def test_429_then_success_retries_and_returns_qty(self):
        monitor = _monitor()
        rate_limited = MagicMock(status_code=429, text="rate limited")
        ok_resp = MagicMock(status_code=200)
        ok_resp.json.return_value = {"qty": "10"}

        with (
            patch(
                "algo.monitoring.position_monitor.requests.get",
                side_effect=[rate_limited, ok_resp],
            ),
            patch("algo.monitoring.position_monitor.time.sleep") as mock_sleep,
        ):
            qty = monitor._fetch_alpaca_qty("https://paper-api.alpaca.markets", "k", "s", "AAPL")

        assert qty == 10
        mock_sleep.assert_called_once()

    def test_404_does_not_retry(self):
        monitor = _monitor()
        not_found = MagicMock(status_code=404, text="not found")

        with patch("algo.monitoring.position_monitor.requests.get", return_value=not_found) as mock_get:
            try:
                monitor._fetch_alpaca_qty("https://paper-api.alpaca.markets", "k", "s", "AAPL")
                raise AssertionError("expected RuntimeError")
            except RuntimeError:
                pass

        assert mock_get.call_count == 1

    def test_timeout_then_success_retries_and_returns_qty(self):
        # Narrower gap found the same day: this loop only inspected response.status_code, so
        # a requests.Timeout/ConnectionError raised by requests.get() itself (no status code
        # exists yet) escaped on the first attempt with zero retries - and unlike the other
        # call sites in this bug class, this one's caller (line ~1201) only catches
        # psycopg2 errors, so an uncaught request exception here crashes the entire
        # corporate-action detection cycle, not just this one symbol.
        monitor = _monitor()
        ok_resp = MagicMock(status_code=200)
        ok_resp.json.return_value = {"qty": "10"}

        with (
            patch(
                "algo.monitoring.position_monitor.requests.get",
                side_effect=[requests.Timeout("timed out"), ok_resp],
            ),
            patch("algo.monitoring.position_monitor.time.sleep") as mock_sleep,
        ):
            qty = monitor._fetch_alpaca_qty("https://paper-api.alpaca.markets", "k", "s", "AAPL")

        assert qty == 10
        mock_sleep.assert_called_once()

    def test_connection_error_exhausts_retries_then_raises(self):
        monitor = _monitor()

        with (
            patch(
                "algo.monitoring.position_monitor.requests.get",
                side_effect=requests.ConnectionError("connection reset"),
            ) as mock_get,
            patch("algo.monitoring.position_monitor.time.sleep"),
        ):
            try:
                monitor._fetch_alpaca_qty("https://paper-api.alpaca.markets", "k", "s", "AAPL")
                raise AssertionError("expected RuntimeError")
            except RuntimeError:
                pass

        assert mock_get.call_count == 3


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
