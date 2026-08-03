"""Regression: delisted/no-data symbols must be marked unavailable in stock_symbols,
not just logged and silently re-discovered (and re-failed on) every subsequent run.

Bug (confirmed live 2026-08-03): symbols like AVNS, KORE, NSA, TMHC had genuinely gone
quiet at the data source (yfinance returned no rows even over a wide lookback window),
but load_prices.py only ever logged "watermark stale, 0 rows, marking failed" - nothing
persisted that determination to stock_symbols.data_unavailable. Every run rediscovered
the same dead symbols, inflating data_loader_status.consecutive_failures/completion_pct
forever, and operators had to hand-patch stock_symbols out of band (a pattern that isn't
repeatable and doesn't self-heal for the next symbol that goes quiet).

Fix: before marking a >2-day-stale, 0-row symbol as failed, confirm with one more fetch
strictly since the symbol's own watermark. If that's also empty, persist
data_unavailable=TRUE with a reason to stock_symbols (via
_mark_symbol_permanently_unavailable) and count it as skipped, not failed - so it stops
being re-discovered on every run. If the confirmation fetch finds real rows newer than
the watermark, preserve the original behavior (mark failed, retry next run) since that's
evidence of a transient gap, not permanent unavailability.

BUG FIX 2026-08-03: the confirmation originally fetched from a fixed `today - 30 days`
anchor instead of from the symbol's own watermark. For any symbol whose last real trade
fell within that 30-day window (i.e. almost every recently-stopped-trading symbol), the
fetch always re-discovered the already-loaded historical row(s) at/before the watermark,
so the confirmation could never come back empty - permanent-unavailable marking was
structurally unreachable, and 280 real symbols (mostly expired SPAC-rights tickers) got
stuck failing 29 consecutive days. Fixed to fetch from `watermark + 1 day` - the only
question that matters is whether anything NEW has shown up since the last successful load.
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from loaders.load_prices import PriceLoader
from utils.infrastructure.timezone import EASTERN_TZ


def _make_loader():
    loader = PriceLoader.__new__(PriceLoader)
    loader.table_name = "price_daily"
    loader.interval = "1d"
    loader.chunk_size = 10_000
    loader._backfill_days = 0
    loader._router = MagicMock()
    loader._stats = {
        "symbols_failed": 0,
        "symbols_processed": 0,
        "symbols_skipped_by_watermark": 0,
        "rows_fetched": 0,
        "rows_quality_dropped": 0,
        "rows_inserted": 0,
        "source_distribution": {},
    }
    loader.transform = lambda rows: rows
    loader._validate_row = lambda row: True
    loader.watermark_from_rows = lambda rows: max(r["date"] for r in rows)
    loader._bulk_insert_mgr = MagicMock()
    loader._bulk_insert_mgr.bulk_insert.return_value = 0
    loader._watermark = MagicMock()
    return loader


class TestPermanentUnavailableMarking:
    def test_stale_symbol_confirmed_dead_gets_marked_unavailable_not_failed(self):
        loader = _make_loader()
        today = datetime.now(EASTERN_TZ).date()
        dead_watermark = today - timedelta(days=10)
        loader._watermark.get_watermarks_bulk.return_value = {"DEAD": dead_watermark}

        def fake_fetch(symbols, since, **kwargs):
            # Both the forced-fresh (7d) batch fetch and the confirmation fetch (since
            # the watermark) come back genuinely empty - this symbol is really gone.
            return {"DEAD": []}

        loader.fetch_batch_incremental = MagicMock(side_effect=fake_fetch)

        with patch("loaders.load_prices.DatabaseContext") as mock_db_ctx:
            mock_cur = MagicMock()
            mock_db_ctx.return_value.__enter__.return_value = mock_cur

            loader._load_batch(["DEAD"])

            mock_cur.execute.assert_called_once()
            sql, params = mock_cur.execute.call_args[0]
            assert "data_unavailable = TRUE" in sql
            assert params[1] == "DEAD"

        assert loader._stats["symbols_failed"] == 0
        assert loader._stats["symbols_skipped_by_watermark"] == 1
        assert loader._stats["symbols_processed"] == 1

        # Confirms the since-watermark confirmation fetch actually happened, not just a re-read.
        confirmation_calls = [
            c for c in loader.fetch_batch_incremental.call_args_list if c.args[1] == dead_watermark + timedelta(days=1)
        ]
        assert len(confirmation_calls) == 1

    def test_stale_symbol_with_newer_data_stays_failed_not_marked(self):
        """A confirmation fetch that finds a row NEWER than the watermark means this is a
        transient gap, not a dead symbol - must preserve the original fail-and-retry
        behavior, not mark it unavailable. (A row OLDER than the watermark would just be
        re-discovering data already loaded - see the 2026-08-03 bug fix above; that must
        NOT be treated as evidence the symbol is still alive.)"""
        loader = _make_loader()
        today = datetime.now(EASTERN_TZ).date()
        stale_watermark = today - timedelta(days=10)
        loader._watermark.get_watermarks_bulk.return_value = {"GAPPY": stale_watermark}

        new_row = {
            "symbol": "GAPPY",
            "date": today - timedelta(days=3),
            "open": 1.0,
            "high": 2.0,
            "low": 0.5,
            "close": 1.5,
            "volume": 100,
        }

        def fake_fetch(symbols, since, **kwargs):
            if since == stale_watermark + timedelta(days=1):
                return {"GAPPY": [dict(new_row)]}
            return {"GAPPY": []}

        loader.fetch_batch_incremental = MagicMock(side_effect=fake_fetch)

        with patch("loaders.load_prices.DatabaseContext") as mock_db_ctx:
            loader._load_batch(["GAPPY"])
            mock_db_ctx.assert_not_called()

        assert loader._stats["symbols_failed"] == 1
        assert loader._stats["symbols_skipped_by_watermark"] == 0

    def test_mark_symbol_permanently_unavailable_writes_expected_update(self):
        loader = _make_loader()
        with patch("loaders.load_prices.DatabaseContext") as mock_db_ctx:
            mock_cur = MagicMock()
            mock_db_ctx.return_value.__enter__.return_value = mock_cur

            loader._mark_symbol_permanently_unavailable("ZOMBIE", "test reason")

            mock_cur.execute.assert_called_once()
            sql, params = mock_cur.execute.call_args[0]
            assert "UPDATE stock_symbols" in sql
            assert "data_unavailable = TRUE" in sql
            assert params == ("test reason", "ZOMBIE")

    def test_mark_symbol_permanently_unavailable_swallows_db_errors(self):
        """A DB failure while persisting the marker must not crash the loader run -
        it just means this symbol gets rediscovered next run, which is safe."""
        loader = _make_loader()
        with patch("loaders.load_prices.DatabaseContext", side_effect=RuntimeError("db down")):
            loader._mark_symbol_permanently_unavailable("ZOMBIE", "test reason")  # must not raise
