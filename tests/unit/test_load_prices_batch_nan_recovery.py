"""Regression: yfinance batch downloads can silently drop individual thin-volume symbols.

Bug (live-confirmed 2026-08-03): yfinance's multi-symbol batch download can return
empty/NaN rows for a single thin-volume/small-cap ticker even when the overall batch
call succeeds and other symbols in the same batch get real data for the same window.
When that symbol's watermark wasn't already stale (>2 days), load_prices.py used to
accept the empty result as "no new data, watermark current" - counted as SUCCESS, never
even reaching the fail-rate gate. Confirmed against 11 real symbols (BIOA, CCRN, CLDI,
FCUV, GAMB, GV, JDZG, MBAV, MYGN, NFBK, UBXG) that lagged 1-3 days in price_daily despite
yf.download(symbol) returning real data for each individually.

Fix: before accepting "watermark current, no rows" at face value, retry with a
single-symbol fetch. If that recovers rows, use them; if the single-symbol retry also
comes back empty, that's unconfirmed (not proof of "no new data") and must count as a
real failure - not a silent skip. See test_symbol_counted_as_failed_when_individual_
refetch_also_empty for the 2026-08-04 fix to a second gap in this same recovery path.
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

from loaders.load_prices import PriceLoader
from utils.infrastructure.timezone import EASTERN_TZ


def _make_loader():
    loader = PriceLoader.__new__(PriceLoader)
    loader.table_name = "price_daily"
    loader.interval = "1d"
    loader.chunk_size = 10_000
    loader._backfill_days = 0
    loader._router = MagicMock()  # `router` is a read-only property backed by `_router`
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
    loader._bulk_insert_mgr.bulk_insert.return_value = 2
    loader._watermark = MagicMock()
    loader._is_eod_pipeline = False
    return loader


def _row(symbol: str, d) -> dict:
    return {
        "symbol": symbol,
        "date": d,
        "open": 1.0,
        "high": 2.0,
        "low": 0.5,
        "close": 1.5,
        "volume": 100,
    }


class TestBatchNanRecovery:
    def test_symbol_recovered_via_individual_refetch_when_batch_returns_empty(self):
        loader = _make_loader()
        today = datetime.now(EASTERN_TZ).date()
        recent_watermark = today - timedelta(days=1)  # 1 day stale: below the >2-day hard-fail threshold
        loader._watermark.get_watermarks_bulk.return_value = {
            "AAPL": recent_watermark,
            "THINVOL": recent_watermark,
        }

        good_row = _row("AAPL", today)
        recovered_row = _row("THINVOL", today)

        def fake_fetch(symbols, since, **kwargs):
            if symbols == ["AAPL", "THINVOL"]:
                # Simulates yfinance's batch call silently NaN-ing THINVOL only.
                return {"AAPL": [dict(good_row)], "THINVOL": []}
            if symbols == ["THINVOL"]:
                # Individual re-fetch recovers the real data yfinance had all along.
                return {"THINVOL": [dict(recovered_row)]}
            raise AssertionError(f"Unexpected symbols argument: {symbols}")

        loader.fetch_batch_incremental = MagicMock(side_effect=fake_fetch)

        loader._load_batch(["AAPL", "THINVOL"])

        # Recovery path taken: THINVOL must NOT be counted as skipped-by-watermark or failed.
        assert loader._stats["symbols_skipped_by_watermark"] == 0
        assert loader._stats["symbols_failed"] == 0
        assert loader._stats["symbols_processed"] == 2

        inserted_rows = loader._bulk_insert_mgr.bulk_insert.call_args[0][0]
        inserted_symbols = {r["symbol"] for r in inserted_rows}
        assert inserted_symbols == {"AAPL", "THINVOL"}

        # Confirms the individual re-fetch actually happened, not just a re-read of the batch result.
        loader.fetch_batch_incremental.assert_any_call(["THINVOL"], recent_watermark)

    def test_symbol_counted_as_failed_when_individual_refetch_also_empty(self):
        """FIX 2026-08-04: if the single-symbol retry ALSO comes back empty, that is not
        confirmation of "genuinely no new data" - it used to be silently accepted as a
        skip/success, which let symbols vanish from price_daily forever with no
        data_unavailable marker and no symbols_failed count (live-reproduced: 103 actively
        traded symbols, including GAMB/GV named in this same BATCH_NAN_RECOVERY comment,
        stuck missing day after day). It must now count as a real failure so the fail-rate
        gate sees it and the existing >2-day-stale escalation path can resolve it on a
        later run."""
        loader = _make_loader()
        today = datetime.now(EASTERN_TZ).date()
        recent_watermark = today - timedelta(days=1)
        loader._watermark.get_watermarks_bulk.return_value = {
            "AAPL": recent_watermark,
            "QUIET": recent_watermark,
        }

        good_row = _row("AAPL", today)

        def fake_fetch(symbols, since, **kwargs):
            if symbols == ["AAPL", "QUIET"]:
                return {"AAPL": [dict(good_row)], "QUIET": []}
            if symbols == ["QUIET"]:
                # Both batch and individual fetch came back empty - unconfirmed, not proof.
                return {"QUIET": []}
            raise AssertionError(f"Unexpected symbols argument: {symbols}")

        loader.fetch_batch_incremental = MagicMock(side_effect=fake_fetch)

        loader._load_batch(["AAPL", "QUIET"])

        assert loader._stats["symbols_skipped_by_watermark"] == 0
        assert loader._stats["symbols_failed"] == 1
        assert loader._stats["symbols_processed"] == 2

        inserted_rows = loader._bulk_insert_mgr.bulk_insert.call_args[0][0]
        assert {r["symbol"] for r in inserted_rows} == {"AAPL"}

    def test_singleton_batch_does_not_retry_itself(self):
        """When _load_batch is already called with a single symbol (e.g. the
        SYMBOL_FALLBACK per-symbol retry path), an empty result must not trigger a
        second, pointless individual re-fetch of the same symbol - and (2026-08-04) is
        counted as a real failure, not a silent skip."""
        loader = _make_loader()
        today = datetime.now(EASTERN_TZ).date()
        recent_watermark = today - timedelta(days=1)
        loader._watermark.get_watermarks_bulk.return_value = {"SOLO": recent_watermark}

        loader.fetch_batch_incremental = MagicMock(return_value={"SOLO": []})

        loader._load_batch(["SOLO"])

        loader.fetch_batch_incremental.assert_called_once_with(["SOLO"], recent_watermark)
        assert loader._stats["symbols_skipped_by_watermark"] == 0
        assert loader._stats["symbols_failed"] == 1
