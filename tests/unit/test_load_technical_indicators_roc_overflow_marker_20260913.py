"""Regression test for the 2026-09-13 fix: a symbol skipped for ROC_OVERFLOW_SKIP used to be
dropped from technical_data_daily entirely for its latest date - no row at all, indistinguishable
from "not yet computed". Root-caused via data_patrol_backlog_report.py's 'needs_fix' review for
the technical_data_daily/trend_template_data coverage-check shortfall (~40 symbols): OptimalLoader
already got a never-silently-drop fix for this exact failure shape (commit 857069987,
unavailable_marker_columns), but VectorizedTechnicalLoader isn't OptimalLoader-based, so that fix
never covered it.

Fixed via _write_roc_overflow_markers: a best-effort, ON CONFLICT DO NOTHING marker insert
(data_unavailable=TRUE, reason set) for each symbol skipped this way, keyed to that symbol's own
last-available price date (not "today", so it still lines up correctly if a symbol's price data
itself lags the rest of the universe).
"""

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

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


class TestRocOverflowMarker:
    def test_skipped_symbol_gets_unavailable_marker_row(self, monkeypatch) -> None:
        loader = VectorizedTechnicalLoader()
        monkeypatch.setattr(loader, "_fetch_spy_prices", lambda *a, **kw: [])

        end_date = date.today()
        prices = _flat_price_series("YYYY", 400, end_date)
        _spike_at(prices, 400 - 10, 1_000_000.0)

        write_cur = MagicMock()

        def fake_db_context(mode, **kwargs):
            ctx = MagicMock()
            ctx.__enter__.return_value = write_cur
            ctx.__exit__.return_value = False
            return ctx

        with patch("loaders.load_technical_indicators.DatabaseContext", side_effect=fake_db_context):
            loader._compute_all_indicators_vectorized(prices)

        assert loader.skipped_symbols_count == 1
        assert write_cur.execute.call_count == 1
        query, params = write_cur.execute.call_args.args
        assert "INSERT INTO technical_data_daily" in query
        assert "ON CONFLICT (symbol, date) DO NOTHING" in query
        symbol, marker_date, reason = params
        assert symbol == "YYYY"
        assert marker_date == end_date
        assert "roc_overflow" in reason

    def test_no_marker_write_when_nothing_skipped(self, monkeypatch) -> None:
        loader = VectorizedTechnicalLoader()
        monkeypatch.setattr(loader, "_fetch_spy_prices", lambda *a, **kw: [])

        end_date = date.today()
        prices = _flat_price_series("ZZZZ", 400, end_date)

        with patch("loaders.load_technical_indicators.DatabaseContext") as mock_ctx:
            loader._compute_all_indicators_vectorized(prices)
            mock_ctx.assert_not_called()

        assert loader.skipped_symbols_count == 0

    def test_marker_write_failure_never_raises(self, monkeypatch) -> None:
        loader = VectorizedTechnicalLoader()
        monkeypatch.setattr(loader, "_fetch_spy_prices", lambda *a, **kw: [])

        end_date = date.today()
        prices = _flat_price_series("YYYY", 400, end_date)
        _spike_at(prices, 400 - 10, 1_000_000.0)

        with patch("loaders.load_technical_indicators.DatabaseContext", side_effect=RuntimeError("db down")):
            result = loader._compute_all_indicators_vectorized(prices)  # must not raise

        assert loader.skipped_symbols_count == 1
        assert "YYYY" not in (result["symbol"].values if not result.empty else [])
