"""Regression test: check_market_circuit_breaker's fetch_quotes/fetch_bars made exactly one
Alpaca API attempt each - the one instance of the retry-on-transient-error bug class (already
fixed in check_single_stock_halt/check_delisting in this same file, and in
order_manager.py/position_monitor.py/exit_engine.py elsewhere) that was missed, and the highest
blast radius of all of them: phase2_circuit_breakers.py fails closed on ANY error from this
check, halting ALL new entries for the rest of the day over a single transient 429/503 on the
market-wide SPY quote/bars check.

Fixed by giving fetch_quotes/fetch_bars the same up-to-3-attempt retry loop already used
elsewhere in this file.
"""

from unittest.mock import MagicMock, patch

import pytest
import requests

from algo.infrastructure.market_events import MarketEventHandler


@pytest.fixture
def handler():
    with (
        patch("algo.infrastructure.market_events.get_credential_manager") as mock_cred_manager,
        patch("algo.infrastructure.market_events.get_alpaca_base_url", return_value="https://api.alpaca.markets"),
    ):
        mock_cm = MagicMock()
        mock_cm.get_alpaca_credentials.return_value = {"key": "k", "secret": "s"}
        mock_cred_manager.return_value = mock_cm
        return MarketEventHandler({"execution_mode": "paper"})


def _quote_resp(status_code, ap=485.0):
    resp = MagicMock(status_code=status_code)
    resp.json.return_value = {"quote": {"ap": ap}}
    return resp


def _bar_resp(status_code, o=500.0):
    resp = MagicMock(status_code=status_code)
    resp.json.return_value = {"bar": {"o": o}}
    return resp


def _routed_get(quote_codes, bar_codes, quote_ap=485.0, bar_o=500.0):
    # fetch_quotes/fetch_bars run in real concurrent threads (ThreadPoolExecutor), so a
    # call-order-based side_effect list would be racy across the two URLs. Route by URL instead.
    quote_iter = iter(quote_codes)
    bar_iter = iter(bar_codes)

    def _get(url, *args, **kwargs):
        if "quotes" in url:
            return _quote_resp(next(quote_iter), ap=quote_ap)
        return _bar_resp(next(bar_iter), o=bar_o)

    return _get


class TestCircuitBreakerQuoteBarsRetryTransientErrors:
    def test_quotes_429_then_success_retries_and_returns_result(self, handler):
        with (
            patch("algo.infrastructure.market_events.get_alpaca_data_url", return_value="https://data.alpaca.markets"),
            patch(
                "algo.infrastructure.market_events.requests.get",
                side_effect=_routed_get(quote_codes=[429, 200], bar_codes=[200]),
            ),
            patch("algo.infrastructure.market_events.time.sleep"),
        ):
            result = handler.check_market_circuit_breaker()

        assert result is None  # 3% down, below the 7% L1 threshold

    def test_bars_503_exhausts_retries_then_fails_closed(self, handler):
        with (
            patch("algo.infrastructure.market_events.get_alpaca_data_url", return_value="https://data.alpaca.markets"),
            patch(
                "algo.infrastructure.market_events.requests.get",
                side_effect=_routed_get(quote_codes=[200], bar_codes=[503, 503, 503]),
            ),
            patch("algo.infrastructure.market_events.time.sleep"),
        ):
            result = handler.check_market_circuit_breaker()

        assert result is not None
        assert result["error"] == "circuit_breaker_check_failed"

    def test_quotes_401_does_not_retry(self, handler):
        with (
            patch("algo.infrastructure.market_events.get_alpaca_data_url", return_value="https://data.alpaca.markets"),
            patch(
                "algo.infrastructure.market_events.requests.get",
                side_effect=_routed_get(quote_codes=[401], bar_codes=[200]),
            ) as mock_get,
        ):
            result = handler.check_market_circuit_breaker()

        assert result is not None
        assert result["error"] == "circuit_breaker_check_failed"
        # 1 call for quotes (no retry on 401) + 1 call for bars = 2, not 3+ (which retries would add)
        assert mock_get.call_count == 2

    def test_quotes_timeout_then_success_retries_and_returns_result(self, handler):
        # Narrower gap found the same day as the 429/503 fix above: the retry loop only
        # inspected response.status_code, so a requests.Timeout/ConnectionError raised by
        # requests.get() itself escaped on the first attempt with zero retries.
        quote_iter = iter([requests.Timeout("timed out"), _quote_resp(200)])

        def _get(url, *args, **kwargs):
            if "quotes" in url:
                item = next(quote_iter)
                if isinstance(item, Exception):
                    raise item
                return item
            return _bar_resp(200)

        with (
            patch("algo.infrastructure.market_events.get_alpaca_data_url", return_value="https://data.alpaca.markets"),
            patch("algo.infrastructure.market_events.requests.get", side_effect=_get),
            patch("algo.infrastructure.market_events.time.sleep"),
        ):
            result = handler.check_market_circuit_breaker()

        assert result is None  # 3% down, below the 7% L1 threshold

    def test_bars_connection_error_exhausts_retries_then_fails_closed(self, handler):
        def _get(url, *args, **kwargs):
            if "quotes" in url:
                return _quote_resp(200)
            raise requests.ConnectionError("connection reset")

        with (
            patch("algo.infrastructure.market_events.get_alpaca_data_url", return_value="https://data.alpaca.markets"),
            patch("algo.infrastructure.market_events.requests.get", side_effect=_get) as mock_get,
            patch("algo.infrastructure.market_events.time.sleep"),
        ):
            result = handler.check_market_circuit_breaker()

        assert result is not None
        assert result["error"] == "circuit_breaker_check_failed"
        # 1 quotes call + 3 bars call attempts = 4
        assert mock_get.call_count == 4


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
