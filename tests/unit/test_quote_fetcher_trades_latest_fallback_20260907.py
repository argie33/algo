"""Regression test for a live-reproduced gap in algo/trading/quote_fetcher.py's
fetch_live_quote(): when /v2/stocks/quotes/latest returns HTTP 200 with no usable bid/ask
and no `lp` (last_price) for a symbol, the function raised immediately with no attempt to
recover a price from /v2/stocks/trades/latest - a distinct IEX data source (last executed
print, vs. the quote endpoint's last NBBO quote) that can be populated even when the quote
side is empty for a thin symbol.

Live-confirmed via algo_exit_check_errors: NUTX (a currently open position, entered
2026-08-27) and CLMB repeatedly failed check_and_execute_exits() this exact way across
multiple sessions (2026-09-02 through 2026-09-04, market open each time) - "Alpaca quote API
returned status 200 but no valid price data for {symbol}". Each occurrence meant the entire
ExitStrategyChain (trailing stop raise, T1/T2/T3 targets, Minervini/RS breaks, distribution
de-risking) could not be evaluated for that position that cycle - not a naked position (the
broker's own resting GTC stop order is unaffected by this), but a real gap in active risk
management for exactly the real-money positions this matters most for.

Fix: fall back to /v2/stocks/trades/latest before giving up. Best-effort only - any failure
in the fallback itself must not change the existing fail-closed RuntimeError behavior.
"""

from unittest.mock import MagicMock, patch

from algo.trading.quote_fetcher import fetch_live_quote


def _empty_quote_response():
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"quotes": {"NUTX": {}}}
    return resp


def _trade_response(price):
    resp = MagicMock(status_code=200)
    resp.json.return_value = {"trades": {"NUTX": {"p": price, "t": "2026-09-04T13:31:00Z"}}}
    return resp


class TestTradesLatestFallback:
    def test_falls_back_to_trades_latest_when_quote_has_no_price(self):
        responses = [_empty_quote_response(), _trade_response(184.5)]
        with (
            patch("algo.trading.quote_fetcher.get_alpaca_credentials", return_value={"key": "k", "secret": "s"}),
            patch("algo.trading.quote_fetcher.get_alpaca_data_url", return_value="https://data.alpaca.markets"),
            patch("algo.trading.quote_fetcher.requests.get", side_effect=responses) as mock_get,
            patch("algo.trading.quote_fetcher.MarketCalendar.is_market_open", return_value=True),
        ):
            price = fetch_live_quote("NUTX", execution_mode="auto")

        assert price == 184.5
        urls_called = [c.args[0] for c in mock_get.call_args_list]
        assert any("trades/latest" in u for u in urls_called), (
            "fetch_live_quote must fall back to /v2/stocks/trades/latest when "
            "quotes/latest has no usable bid/ask/last_price"
        )

    def test_raises_when_both_quotes_and_trades_are_empty(self):
        """The fallback must not mask a genuine outage - if trades/latest is also empty,
        the original fail-closed RuntimeError behavior must be unchanged."""
        empty_trades_resp = MagicMock(status_code=200)
        empty_trades_resp.json.return_value = {"trades": {}}
        responses = [_empty_quote_response(), empty_trades_resp]
        with (
            patch("algo.trading.quote_fetcher.get_alpaca_credentials", return_value={"key": "k", "secret": "s"}),
            patch("algo.trading.quote_fetcher.get_alpaca_data_url", return_value="https://data.alpaca.markets"),
            patch("algo.trading.quote_fetcher.requests.get", side_effect=responses),
            patch("algo.trading.quote_fetcher.MarketCalendar.is_market_open", return_value=True),
        ):
            try:
                fetch_live_quote("NUTX", execution_mode="auto")
                raise AssertionError("expected RuntimeError")
            except RuntimeError as e:
                assert "no valid price data" in str(e)

    def test_fallback_exception_does_not_mask_original_error(self):
        """A network error in the fallback call itself must not raise a different/opaque
        exception - it must be swallowed so the caller still gets the original, informative
        fail-closed RuntimeError."""
        import requests as requests_module

        responses = [_empty_quote_response(), requests_module.ConnectionError("dns fail")]
        with (
            patch("algo.trading.quote_fetcher.get_alpaca_credentials", return_value={"key": "k", "secret": "s"}),
            patch("algo.trading.quote_fetcher.get_alpaca_data_url", return_value="https://data.alpaca.markets"),
            patch("algo.trading.quote_fetcher.requests.get", side_effect=responses),
            patch("algo.trading.quote_fetcher.MarketCalendar.is_market_open", return_value=True),
        ):
            try:
                fetch_live_quote("NUTX", execution_mode="auto")
                raise AssertionError("expected RuntimeError")
            except RuntimeError as e:
                assert "no valid price data" in str(e)
