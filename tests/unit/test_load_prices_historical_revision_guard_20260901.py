"""Regression test: PriceLoader._guard_against_historical_price_revision (loaders/load_prices.py).

Added 2026-09-01 (goal session - "figure out what is best and do it" after live-tracing a real
data corruption bug). Root cause: Yahoo Finance retroactively split-adjusts its "Close" field
once a real split is processed on their backend, regardless of yfinance's auto_adjust parameter.
This loader's own backfill path (self._backfill_days > 0) deliberately skips the watermark-based
WRITE TRIM, so a backfill run can re-fetch and unconditionally overwrite already-recorded
historical price_daily rows via the generic bulk upsert - letting Yahoo's retroactive adjustment
silently rewrite history. Live-confirmed on MNST (real 2:1 split ~2026-08-08/10): pre-split
dates got overwritten with the already-halved close on a later run, producing an OSCILLATING
price series that fed a volatility_60d of 374.5% annualized into a large, stable company's Risk
score (see loaders/load_risk_metrics_daily.py's 2026-09-01 adj_close-preference fix, which
addressed the downstream symptom - this guard addresses the ingestion-layer root cause).

See PRICE_HISTORY_PROTECTED_AFTER_DAYS/PRICE_HISTORY_MAX_SILENT_REVISION_PCT's own
module-level docstring in loaders/load_prices.py for the full evidence trail.
"""

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

from loaders.load_prices import PriceLoader


def _make_loader(table_name: str = "price_daily") -> PriceLoader:
    loader = PriceLoader.__new__(PriceLoader)
    loader.table_name = table_name
    return loader


def _db_context_mock(existing_rows: list[tuple[str, date, float]]) -> MagicMock:
    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = existing_rows
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_cur
    outer = MagicMock(return_value=mock_ctx)
    return outer


class TestOldDateLargeRevisionBlocked:
    def test_old_date_with_large_revision_is_dropped(self) -> None:
        loader = _make_loader()
        old_date = date.today() - timedelta(days=30)
        # existing close $95.45, incoming close $47.23 - a ~50.5% "revision" to already-
        # settled history, exactly MNST's live pattern.
        rows = [{"symbol": "MNST", "date": old_date, "close": 47.23, "data_source": "yfinance"}]

        with patch("loaders.load_prices.DatabaseContext", _db_context_mock([("MNST", old_date, 95.45)])):
            kept = loader._guard_against_historical_price_revision(rows)

        assert kept == []

    def test_old_date_with_small_revision_passes_through(self) -> None:
        """A legitimate small correction (e.g. rounding/precision fix) must not be blocked -
        only large, split-like discontinuities are."""
        loader = _make_loader()
        old_date = date.today() - timedelta(days=30)
        rows = [{"symbol": "AAPL", "date": old_date, "close": 100.50, "data_source": "alpaca"}]

        with patch("loaders.load_prices.DatabaseContext", _db_context_mock([("AAPL", old_date, 100.00)])):
            kept = loader._guard_against_historical_price_revision(rows)

        assert kept == rows


class TestNewFillsAndRecentDatesUnaffected:
    def test_old_date_with_no_existing_row_passes_through(self) -> None:
        """A genuinely new (symbol, date) pair - e.g. backfilling a real gap - is a fill, not
        an overwrite, and must never be blocked."""
        loader = _make_loader()
        old_date = date.today() - timedelta(days=30)
        rows = [{"symbol": "NEWCO", "date": old_date, "close": 12.34, "data_source": "yfinance"}]

        with patch("loaders.load_prices.DatabaseContext", _db_context_mock([])):
            kept = loader._guard_against_historical_price_revision(rows)

        assert kept == rows

    def test_recent_date_always_passes_through_even_with_large_revision(self) -> None:
        """Recent dates (within PRICE_HISTORY_PROTECTED_AFTER_DAYS) stay freely correctable -
        genuine T+1/T+2 vendor settlement revisions are real and expected."""
        loader = _make_loader()
        recent_date = date.today() - timedelta(days=1)
        rows = [{"symbol": "MNST", "date": recent_date, "close": 47.23, "data_source": "yfinance"}]

        # Guard must not even need to query for purely-recent batches.
        with patch("loaders.load_prices.DatabaseContext", _db_context_mock([("MNST", recent_date, 95.45)])):
            kept = loader._guard_against_historical_price_revision(rows)

        assert kept == rows

    def test_mixed_batch_only_drops_the_offending_row(self) -> None:
        loader = _make_loader()
        old_date = date.today() - timedelta(days=30)
        recent_date = date.today() - timedelta(days=1)
        rows = [
            {"symbol": "MNST", "date": old_date, "close": 47.23, "data_source": "yfinance"},
            {"symbol": "AAPL", "date": old_date, "close": 100.5, "data_source": "alpaca"},
            {"symbol": "MNST", "date": recent_date, "close": 46.0, "data_source": "yfinance"},
        ]

        with patch(
            "loaders.load_prices.DatabaseContext",
            _db_context_mock([("MNST", old_date, 95.45), ("AAPL", old_date, 100.4)]),
        ):
            kept = loader._guard_against_historical_price_revision(rows)

        kept_keys = {(r["symbol"], r["date"]) for r in kept}
        assert ("MNST", old_date) not in kept_keys
        assert ("AAPL", old_date) in kept_keys
        assert ("MNST", recent_date) in kept_keys


class TestGuardScopedToDailyPriceTables:
    def test_guard_is_only_wired_for_price_daily_and_etf_price_daily(self) -> None:
        """Weekly/monthly derived tables and other PriceLoader table_name values must not be
        silently affected by this guard's own semantics changing."""
        import inspect

        source = inspect.getsource(PriceLoader._load_batch)
        assert 'self.table_name in ("price_daily", "etf_price_daily")' in source
        assert "_guard_against_historical_price_revision" in source


class TestQueryFailureDoesNotBlockTheWholeBatch:
    def test_db_error_during_guard_query_falls_back_to_passing_rows_through(self) -> None:
        import psycopg2

        loader = _make_loader()
        old_date = date.today() - timedelta(days=30)
        rows = [{"symbol": "MNST", "date": old_date, "close": 47.23, "data_source": "yfinance"}]

        def _raise(*_args: object, **_kwargs: object) -> None:
            raise psycopg2.OperationalError("connection lost")

        mock_ctx = MagicMock()
        mock_ctx.__enter__.side_effect = _raise
        with patch("loaders.load_prices.DatabaseContext", return_value=mock_ctx):
            kept = loader._guard_against_historical_price_revision(rows)

        assert kept == rows
