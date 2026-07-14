"""Routing tests for PRICE_DATA_SOURCE=alpaca with per-symbol yfinance residual fallback."""

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
            "date": "2026-07-13",
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


def test_alpaca_primary_merges_residual_from_yfinance(
    router: DataSourceRouter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Symbols Alpaca doesn't serve (caret indexes, OTC stragglers) come from yfinance."""
    monkeypatch.setenv("PRICE_DATA_SOURCE", "alpaca")
    symbols = ["AAPL", "BK", "^GSPC"]

    def fake_alpaca(syms: list[str], start: date, end: date) -> dict[str, Any]:
        return {"AAPL": _rows("AAPL"), "BK": None, "^GSPC": None}

    def fake_yfinance(syms: list[str], start: date, end: date, interval: str = "1d") -> dict[str, Any]:
        assert sorted(syms) == ["BK", "^GSPC"], "yfinance must only see the Alpaca residual"
        return {s: _rows(s) for s in syms}

    with (
        patch.object(router, "_fetch_alpaca_ohlcv_batch", side_effect=fake_alpaca),
        patch.object(router, "_fetch_yfinance_ohlcv_batch", side_effect=fake_yfinance),
    ):
        result = router.fetch_ohlcv_batch(symbols, START, END)

    assert all(result[s] == _rows(s) for s in symbols)
    assert router.last_source == "alpaca"


def test_alpaca_wholesale_failure_falls_back_to_full_yfinance(
    router: DataSourceRouter, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PRICE_DATA_SOURCE", "alpaca")
    symbols = ["AAPL", "MSFT"]

    def fake_yfinance(syms: list[str], start: date, end: date, interval: str = "1d") -> dict[str, Any]:
        assert syms == symbols, "wholesale Alpaca failure must re-fetch the FULL batch"
        return {s: _rows(s) for s in syms}

    with (
        patch.object(router, "_fetch_alpaca_ohlcv_batch", side_effect=RuntimeError("alpaca outage")),
        patch.object(router, "_fetch_yfinance_ohlcv_batch", side_effect=fake_yfinance),
    ):
        result = router.fetch_ohlcv_batch(symbols, START, END)

    assert all(result[s] == _rows(s) for s in symbols)
    assert router.last_source == "yfinance"


def test_yfinance_residual_failure_keeps_alpaca_batch(
    router: DataSourceRouter, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A yfinance blip on the residual must not discard the successful Alpaca batch."""
    monkeypatch.setenv("PRICE_DATA_SOURCE", "alpaca")
    symbols = ["AAPL", "BK"]

    def fake_alpaca(syms: list[str], start: date, end: date) -> dict[str, Any]:
        return {"AAPL": _rows("AAPL"), "BK": None}

    with (
        patch.object(router, "_fetch_alpaca_ohlcv_batch", side_effect=fake_alpaca),
        patch.object(router, "_fetch_yfinance_ohlcv_batch", side_effect=RuntimeError("yf blip")),
    ):
        result = router.fetch_ohlcv_batch(symbols, START, END)

    assert result["AAPL"] == _rows("AAPL")
    assert result["BK"] is None
    assert router.last_source == "alpaca"


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
