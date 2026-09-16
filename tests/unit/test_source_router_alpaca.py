"""Routing tests for PRICE_DATA_SOURCE=alpaca.

REMOVED 2026-09-15 (explicit decision, not a bug fix): equities no longer get any
yfinance residual/wholesale fallback - an Alpaca miss leaves the symbol unavailable
instead of silently substituting a different vendor's number (live-caught: FFAI's
alpaca/yfinance feeds disagreed by ~150x for several days around a reverse split,
undetected until then because the blend made it invisible). Caret index symbols
(^VIX etc.) still route to yfinance unconditionally - Alpaca's stock endpoints
cannot serve them at all (confirmed live, both /v2/stocks and every /v1beta1/indices
guess 404/403), so there's no "which source is right" ambiguity for those.
"""

from datetime import date
from typing import Any
from unittest.mock import patch

import pytest

from utils.data.source_router import DataSourceRouter

START = date(2026, 7, 8)
END = date(2026, 7, 14)


def _rows(symbol: str) -> list[dict[str, Any]]:
    return [
        {
            "symbol": symbol,
            "date": "2026-07-14",
            "open": 1.0,
            "high": 2.0,
            "low": 0.5,
            "close": 1.5,
            "volume": 100,
        }
    ]


@pytest.fixture
def router() -> DataSourceRouter:
    return DataSourceRouter()


def test_alpaca_primary_routes_index_symbols_to_yfinance_only(
    router: DataSourceRouter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Caret index symbols always go to yfinance (Alpaca can't serve them at all);
    real equities never fall back to yfinance even when Alpaca doesn't serve them."""
    monkeypatch.setenv("PRICE_DATA_SOURCE", "alpaca")
    symbols = ["AAPL", "BK", "^GSPC"]

    def fake_alpaca(syms: list[str], start: date, end: date) -> dict[str, Any]:
        assert sorted(syms) == ["AAPL", "BK"], "Alpaca must only be asked for real equities, never caret symbols"
        aapl_rows = _rows("AAPL")
        for row in aapl_rows:
            row["_source_name"] = "alpaca"
        return {"AAPL": aapl_rows, "BK": None}

    def fake_yfinance(syms: list[str], start: date, end: date, interval: str = "1d") -> dict[str, Any]:
        assert syms == ["^GSPC"], "yfinance must only be asked for index symbols, never equities"
        return {s: _rows(s) for s in syms}

    with (
        patch.object(router, "_fetch_alpaca_ohlcv_batch", side_effect=fake_alpaca),
        patch.object(router, "_fetch_yfinance_ohlcv_batch", side_effect=fake_yfinance),
    ):
        result = router.fetch_ohlcv_batch(symbols, START, END)

    assert result["AAPL"] is not None, "AAPL should have data from Alpaca"
    assert result["BK"] is None, "BK has no yfinance fallback - Alpaca not serving it means unavailable"
    assert result["^GSPC"] is not None, "^GSPC should have data from yfinance (Alpaca can't serve indexes)"

    assert all(row.get("_source_name") == "alpaca" for row in result["AAPL"]), "AAPL rows should be marked as alpaca"
    assert all(row.get("_source_name") == "yfinance" for row in result["^GSPC"]), (
        "^GSPC rows should be marked as yfinance"
    )


def test_alpaca_wholesale_failure_leaves_equities_unavailable(
    router: DataSourceRouter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A wholesale Alpaca outage must NOT silently substitute yfinance for equities -
    the gap must surface as unavailable so it gets investigated/retried, not masked."""
    monkeypatch.setenv("PRICE_DATA_SOURCE", "alpaca")
    symbols = ["AAPL", "MSFT"]

    with (
        patch.object(router, "_fetch_alpaca_ohlcv_batch", side_effect=RuntimeError("alpaca outage")),
        patch.object(router, "_fetch_yfinance_ohlcv_batch") as yf_mock,
    ):
        result = router.fetch_ohlcv_batch(symbols, START, END)

    yf_mock.assert_not_called()
    assert result["AAPL"] is None
    assert result["MSFT"] is None


def test_alpaca_partial_batch_leaves_unserved_equity_none(
    router: DataSourceRouter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A symbol Alpaca doesn't serve within an otherwise-successful batch stays
    unavailable - no yfinance call happens for it at all (equities never fall back)."""
    monkeypatch.setenv("PRICE_DATA_SOURCE", "alpaca")
    symbols = ["AAPL", "BK"]

    def fake_alpaca(syms: list[str], start: date, end: date) -> dict[str, Any]:
        return {"AAPL": _rows("AAPL"), "BK": None}

    with (
        patch.object(router, "_fetch_alpaca_ohlcv_batch", side_effect=fake_alpaca),
        patch.object(router, "_fetch_yfinance_ohlcv_batch") as yf_mock,
    ):
        result = router.fetch_ohlcv_batch(symbols, START, END)

    yf_mock.assert_not_called()
    assert result["AAPL"] == _rows("AAPL")
    assert result["BK"] is None
    assert router.last_source == "alpaca"


def test_alpaca_stale_rows_are_kept_as_is_not_backfilled_from_yfinance(
    router: DataSourceRouter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A symbol with real Alpaca rows that stop short of `end` is left as-is - no
    yfinance backfill for equities, even for just the missing tail.

    Superseded 2026-09-15: this used to test that a stale/gapping Alpaca response
    triggered a yfinance residual fetch (the 2026-08-22 fix). That blending is gone
    by explicit decision - a stale equity row should surface as a real gap to
    investigate, not be quietly patched from a second vendor.
    """
    monkeypatch.setenv("PRICE_DATA_SOURCE", "alpaca")
    symbols = ["AAPL", "STALE"]

    def fake_alpaca(syms: list[str], start: date, end: date) -> dict[str, Any]:
        aapl_rows = _rows("AAPL")
        # STALE has real Alpaca data, but the last row is one day short of `end`.
        stale_rows = [{**_rows("STALE")[0], "date": "2026-07-13"}]
        return {"AAPL": aapl_rows, "STALE": stale_rows}

    with (
        patch.object(router, "_fetch_alpaca_ohlcv_batch", side_effect=fake_alpaca),
        patch.object(router, "_fetch_yfinance_ohlcv_batch") as yf_mock,
    ):
        result = router.fetch_ohlcv_batch(symbols, START, END)

    yf_mock.assert_not_called()
    assert result["AAPL"] == _rows("AAPL")
    assert result["STALE"][0]["date"] == "2026-07-13", "STALE keeps Alpaca's real (if lagging) data, untouched"


def test_default_source_never_touches_alpaca(router: DataSourceRouter, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PRICE_DATA_SOURCE", raising=False)
    symbols = ["AAPL"]

    def fake_yfinance(syms: list[str], start: date, end: date, interval: str = "1d") -> dict[str, Any]:
        return {s: _rows(s) for s in syms}

    with (
        patch.object(router, "_fetch_alpaca_ohlcv_batch") as alpaca_mock,
        patch.object(router, "_fetch_yfinance_ohlcv_batch", side_effect=fake_yfinance),
    ):
        result = router.fetch_ohlcv_batch(symbols, START, END)

    alpaca_mock.assert_not_called()
    assert result["AAPL"] == _rows("AAPL")


class TestMarketCloseGateChecksConfiguredSource:
    """check_market_close_data_available_fast is the EOD pipeline's go/no-go gate,
    called before load_prices.py starts the real fetch. It previously always probed
    yfinance regardless of PRICE_DATA_SOURCE, so with PRICE_DATA_SOURCE=alpaca the
    gate checked a source that had nothing to do with what the loader was actually
    about to fetch from - a slow/rate-limited yfinance could stall or fail the whole
    daily load even while Alpaca (the real, configured source) already had the day's
    data ready."""

    def test_alpaca_configured_checks_alpaca_not_yfinance(
        self, router: DataSourceRouter, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("PRICE_DATA_SOURCE", "alpaca")

        with (
            patch.object(router, "_check_alpaca_market_close_data_available", return_value=True) as alpaca_check,
        ):
            result = router.check_market_close_data_available_fast(symbol="SPY", timeout_sec=15)

        alpaca_check.assert_called_once_with("SPY", 15)
        assert result is True

    def test_default_source_still_checks_yfinance(
        self, router: DataSourceRouter, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("PRICE_DATA_SOURCE", raising=False)

        with patch.object(router, "_check_alpaca_market_close_data_available") as alpaca_check:
            with patch("utils.data.source_router.yf", None):
                # yf=None short-circuits to False without needing a real network call,
                # while still proving the alpaca path was never touched.
                result = router.check_market_close_data_available_fast(symbol="SPY", timeout_sec=15)

        alpaca_check.assert_not_called()
        assert result is False

    def test_alpaca_check_reflects_fetch_daily_bars_result(
        self, router: DataSourceRouter, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("PRICE_DATA_SOURCE", "alpaca")

        class _FakeAlpaca:
            def __init__(self, timeout_sec: float) -> None:
                self.timeout_sec = timeout_sec

            def fetch_daily_bars(self, symbols: list[str], start: date, end: date) -> dict[str, Any]:
                return {"SPY": _rows("SPY")}

        with patch("utils.external.alpaca_market_data.AlpacaMarketData", _FakeAlpaca):
            result = router.check_market_close_data_available_fast(symbol="SPY", timeout_sec=15)

        assert result is True

    def test_alpaca_check_false_when_no_bars_yet(
        self, router: DataSourceRouter, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("PRICE_DATA_SOURCE", "alpaca")

        class _FakeAlpacaEmpty:
            def __init__(self, timeout_sec: float) -> None:
                pass

            def fetch_daily_bars(self, symbols: list[str], start: date, end: date) -> dict[str, Any]:
                return {}

        with patch("utils.external.alpaca_market_data.AlpacaMarketData", _FakeAlpacaEmpty):
            result = router.check_market_close_data_available_fast(symbol="SPY", timeout_sec=15)

        assert result is False
