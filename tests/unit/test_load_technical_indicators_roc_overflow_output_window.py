"""Regression test for the 2026-08-17 ROC-overflow output-window fix
(loaders/load_technical_indicators.py's _compute_all_indicators_vectorized).

Found live via reference_then_morning_after_signals.log (20+ symbols/run hitting this):
the per-symbol price window fetched for indicator computation spans ~400 calendar days
(252 trading days for roc_252d plus MA/RSI warmup buffer), but only the most recent 30
days are ever written to technical_indicators - everything older is pure warmup. The
original ROC-magnitude guard ran over the FULL 400-day window and skipped the ENTIRE
symbol - discarding its otherwise-valid CURRENT indicators too - whenever ANY single day
anywhere in the ~370 days of warmup-only history had an extreme ROC value (a real but
long-past crash/reorg/bad tick), even though that day was never going to be written to
the DB either way.

This test proves: (1) an extreme ROC value that falls entirely within the warmup-only
portion of the window (never persisted) gets clipped, and the symbol's current-window
indicators still compute and get returned; (2) an extreme ROC value that falls inside
the actual 30-day output window still correctly skips the symbol (the original safety
behavior is preserved for cases that would actually corrupt a written row).
"""

from datetime import date, timedelta

from loaders.load_technical_indicators import VectorizedTechnicalLoader


def _flat_price_series(symbol: str, num_days: int, end_date: date, close: float = 10.0) -> list[dict]:
    return [
        {
            "symbol": symbol,
            "date": (end_date - timedelta(days=num_days - 1 - i)).isoformat(),
            "open": close,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": 1_000_000,
        }
        for i in range(num_days)
    ]


def _spike_at(prices: list[dict], index: int, spiked_close: float) -> None:
    row = dict(prices[index])
    row["close"] = spiked_close
    row["high"] = max(row["high"], spiked_close * 1.01)
    prices[index] = row


class TestRocOverflowOutputWindow:
    def test_warmup_only_outlier_clipped_not_skipped(self, monkeypatch) -> None:
        loader = VectorizedTechnicalLoader()
        monkeypatch.setattr(loader, "_fetch_spy_prices", lambda *a, **kw: [])

        end_date = date.today()
        prices = _flat_price_series("ZZZZ", 400, end_date)
        # A >1000x single-day spike, 395 days before end_date - deep in the warmup-only
        # region, and far enough back that even roc_252d for a row inside the last 30
        # output days can't reach it (252-day lookback from the newest output row lands
        # around index 400-1-252=147, comfortably after this spike at index 5).
        _spike_at(prices, 5, 1_000_000.0)

        result = loader._compute_all_indicators_vectorized(prices)

        assert not result.empty
        assert "ZZZZ" in result["symbol"].values
        assert loader.skipped_symbols_count == 0
        # The most recent row's indicators should be real numbers, not dropped.
        latest = result.sort_values("date").iloc[-1]
        assert latest["rsi"] == latest["rsi"]  # not NaN

    def test_output_window_outlier_still_skips_symbol(self, monkeypatch) -> None:
        loader = VectorizedTechnicalLoader()
        monkeypatch.setattr(loader, "_fetch_spy_prices", lambda *a, **kw: [])

        end_date = date.today()
        prices = _flat_price_series("YYYY", 400, end_date)
        # Same magnitude spike, but only 10 days before end_date - inside the 30-day
        # output window this loader actually writes to the DB.
        _spike_at(prices, 400 - 10, 1_000_000.0)

        result = loader._compute_all_indicators_vectorized(prices)

        assert "YYYY" not in (result["symbol"].values if not result.empty else [])
        assert loader.skipped_symbols_count == 1
