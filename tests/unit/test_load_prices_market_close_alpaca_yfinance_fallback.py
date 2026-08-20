"""Regression: a transient Alpaca outage in the market-close *readiness check* used to
kill the whole day's price load, even though the actual bar-fetch path already falls
back to yfinance on wholesale Alpaca failure (source_router._alpaca_batch_or_none).

Live-confirmed 3x in 3 days (2026-08-18/19/20): short bursts of Alpaca 401s during the
readiness check exhausted its 5-consecutive-error circuit breaker and raised a fatal
RuntimeError before ever reaching the resilient fetch path - despite the very next
scheduled run each day succeeding with the identical credentials, proving the outage
was transient. Fix: try yfinance directly as a last resort before giving up.
"""

import datetime as dt_module
from datetime import datetime as real_datetime
from unittest.mock import MagicMock

import pytest

from algo.infrastructure import MarketCalendar
from loaders.load_prices import PriceLoader
from utils.infrastructure.timezone import EASTERN_TZ

_FIXED_NOW = real_datetime(2026, 8, 20, 16, 20, 0, tzinfo=EASTERN_TZ)  # 20min after 4PM ET close


class _FixedDatetime(real_datetime):
    @classmethod
    def now(cls, tz=None):
        return _FIXED_NOW.astimezone(tz) if tz is not None else _FIXED_NOW


def _make_loader():
    loader = PriceLoader.__new__(PriceLoader)
    loader.interval = "1d"
    loader._router = MagicMock()
    return loader


@pytest.fixture(autouse=True)
def _fixed_trading_time(monkeypatch):
    monkeypatch.setattr(dt_module, "datetime", _FixedDatetime)
    monkeypatch.setattr(MarketCalendar, "is_trading_day", staticmethod(lambda d: True))
    monkeypatch.setattr("loaders.load_prices.time.sleep", lambda _seconds: None)


class TestMarketCloseAlpacaFallsBackToYfinance:
    def test_repeated_alpaca_failures_fall_back_to_yfinance_before_raising(self, monkeypatch):
        monkeypatch.setenv("PRICE_DATA_SOURCE", "alpaca")
        loader = _make_loader()

        # Every Alpaca-path call errors; the one yfinance (force_source) call succeeds.
        def fake_check(symbol="SPY", timeout_sec=15, force_source=None):
            if force_source == "yfinance":
                return True
            raise RuntimeError("Error checking Alpaca market close data for SPY: 401")

        loader._router.check_market_close_data_available_fast.side_effect = fake_check

        result = loader._check_market_close_data_available(max_wait_sec=30)

        assert result is True
        # Confirms the fallback call was actually made with force_source="yfinance",
        # not just that *some* call happened to return True.
        fallback_calls = [
            c
            for c in loader._router.check_market_close_data_available_fast.call_args_list
            if c.kwargs.get("force_source") == "yfinance"
        ]
        assert fallback_calls, "expected a yfinance force_source fallback call after Alpaca circuit-breaker trip"

    def test_alpaca_and_yfinance_fallback_both_failing_still_raises(self, monkeypatch):
        monkeypatch.setenv("PRICE_DATA_SOURCE", "alpaca")
        loader = _make_loader()

        def fake_check(symbol="SPY", timeout_sec=15, force_source=None):
            raise RuntimeError("Error checking Alpaca market close data for SPY: 401")

        loader._router.check_market_close_data_available_fast.side_effect = fake_check

        with pytest.raises(RuntimeError, match="consecutive failures"):
            loader._check_market_close_data_available(max_wait_sec=30)

    def test_yfinance_primary_source_has_no_fallback_path(self, monkeypatch):
        """When PRICE_DATA_SOURCE=yfinance (the default), there is no secondary source
        to fall back to - repeated failures must still raise, not loop forever."""
        monkeypatch.setenv("PRICE_DATA_SOURCE", "yfinance")
        loader = _make_loader()
        loader._router.check_market_close_data_available_fast.side_effect = RuntimeError(
            "Error checking market close data for SPY: connection reset"
        )

        with pytest.raises(RuntimeError, match="consecutive failures"):
            loader._check_market_close_data_available(max_wait_sec=30)

        # No force_source="yfinance" fallback call should have been attempted -
        # yfinance IS the primary here, there's nothing to fall back to.
        for c in loader._router.check_market_close_data_available_fast.call_args_list:
            assert c.kwargs.get("force_source") is None
