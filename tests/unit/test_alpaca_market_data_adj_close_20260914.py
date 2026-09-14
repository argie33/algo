"""Coverage for AlpacaMarketData.fetch_daily_bars' adj_close merge (added 2026-09-14, /goal
scores-data-completeness sweep). Alpaca's raw (`adjustment=raw`) bars never carried a distinct
adjusted-close field, so every Alpaca-sourced price_daily row had a NULL adj_close - unlike the
yfinance path, which has always fallen back to close when a distinct Adj Close is unavailable.
fetch_daily_bars now does a second `adjustment=all` pass and merges it in, falling back to raw
close only when that second pass is missing a given (symbol, date).
"""

from datetime import date
from unittest.mock import MagicMock, patch

from utils.external.alpaca_market_data import AlpacaMarketData


def _bars_response(bars_by_symbol: dict) -> MagicMock:
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = {"bars": bars_by_symbol, "next_page_token": None}
    return resp


class TestFetchDailyBarsAdjClose:
    def test_adj_close_merged_from_second_pass(self) -> None:
        """A symbol with a real split gets a distinct, correctly-adjusted adj_close."""
        client = AlpacaMarketData(feed="iex")
        client._headers = {"APCA-API-KEY-ID": "test", "APCA-API-SECRET-KEY": "test"}
        raw_resp = _bars_response(
            {"MNST": [{"t": "2026-08-07T04:00:00Z", "o": 90, "h": 91, "l": 89, "c": 90.36, "v": 1000}]}
        )
        adjusted_resp = _bars_response(
            {"MNST": [{"t": "2026-08-07T04:00:00Z", "o": 45, "h": 45.5, "l": 44.5, "c": 45.18, "v": 1000}]}
        )
        with patch.object(client._session, "get", side_effect=[raw_resp, adjusted_resp]) as mock_get:
            result = client.fetch_daily_bars(["MNST"], date(2026, 8, 7), date(2026, 8, 7))

        assert mock_get.call_count == 2
        # First call is the raw pass, second is the adjustment=all pass.
        assert mock_get.call_args_list[0].kwargs["params"]["adjustment"] == "raw"
        assert mock_get.call_args_list[1].kwargs["params"]["adjustment"] == "all"
        row = result["MNST"][0]
        assert row["close"] == 90.36
        assert row["adj_close"] == 45.18

    def test_adj_close_falls_back_to_close_when_adjusted_pass_missing_date(self) -> None:
        """A (symbol, date) present in the raw pass but absent from the adjusted pass still gets
        a non-NULL adj_close (falls back to raw close, same convention as the yfinance path)."""
        client = AlpacaMarketData(feed="iex")
        client._headers = {"APCA-API-KEY-ID": "test", "APCA-API-SECRET-KEY": "test"}
        raw_resp = _bars_response(
            {"AAPL": [{"t": "2026-08-07T04:00:00Z", "o": 200, "h": 201, "l": 199, "c": 200.5, "v": 1000}]}
        )
        adjusted_resp = _bars_response({"AAPL": []})
        with patch.object(client._session, "get", side_effect=[raw_resp, adjusted_resp]):
            result = client.fetch_daily_bars(["AAPL"], date(2026, 8, 7), date(2026, 8, 7))

        row = result["AAPL"][0]
        assert row["adj_close"] == row["close"] == 200.5

    def test_adj_close_falls_back_when_adjusted_fetch_raises(self) -> None:
        """If the adjusted-close pass errors entirely, the whole batch still returns rows with a
        non-NULL adj_close (fallback to raw close) rather than propagating the failure."""
        client = AlpacaMarketData(feed="iex")
        client._headers = {"APCA-API-KEY-ID": "test", "APCA-API-SECRET-KEY": "test"}
        raw_resp = _bars_response(
            {"MSFT": [{"t": "2026-08-07T04:00:00Z", "o": 400, "h": 401, "l": 399, "c": 400.25, "v": 1000}]}
        )
        with patch.object(client._session, "get", side_effect=[raw_resp, RuntimeError("network down")]):
            result = client.fetch_daily_bars(["MSFT"], date(2026, 8, 7), date(2026, 8, 7))

        row = result["MSFT"][0]
        assert row["adj_close"] == row["close"] == 400.25

    def test_no_split_symbol_close_equals_adj_close(self) -> None:
        """A symbol with no corporate action in the window has close == adj_close, matching
        the established yfinance-path convention for a distinct-but-identical Adj Close."""
        client = AlpacaMarketData(feed="iex")
        client._headers = {"APCA-API-KEY-ID": "test", "APCA-API-SECRET-KEY": "test"}
        raw_resp = _bars_response(
            {"KO": [{"t": "2026-08-07T04:00:00Z", "o": 70, "h": 71, "l": 69, "c": 70.5, "v": 1000}]}
        )
        adjusted_resp = _bars_response(
            {"KO": [{"t": "2026-08-07T04:00:00Z", "o": 70, "h": 71, "l": 69, "c": 70.5, "v": 1000}]}
        )
        with patch.object(client._session, "get", side_effect=[raw_resp, adjusted_resp]):
            result = client.fetch_daily_bars(["KO"], date(2026, 8, 7), date(2026, 8, 7))

        row = result["KO"][0]
        assert row["close"] == row["adj_close"] == 70.5
