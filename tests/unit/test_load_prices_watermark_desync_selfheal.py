"""Regression test for the 2026-08-10 fix: PriceLoader._load_batch() trusted
loader_watermarks blindly, even when it desyncs from the actual price table.

loader_watermarks advances independently of the data INSERT (a separate write, not the
same transaction). If a watermark write ever landed without its data actually persisting,
the watermark can claim dates the real table doesn't have - and the per-symbol write-trim
in _load_batch discards every freshly-fetched row that isn't strictly newer than that
(wrong, too-advanced) watermark, silently skipping the symbol forever.

Live-reproduced 2026-08-10: SPY/QQQ/IWM's `load_prices` watermark in `etf_price_daily` was
'2026-08-10' (today) but last written 2026-07-10 - a month stale - while the real table's
MAX(date) for those symbols was stuck at 2026-08-05. GLD/TLT's watermark, by contrast,
correctly matched their own real data and were unaffected.

This is the identical bug class already fixed for the SEC loader family - see
tests/unit/test_sec_base_watermark_table_desync_selfheal.py - applied here to the price
loader's batch path.
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from loaders.load_prices import PriceLoader
from utils.infrastructure.timezone import EASTERN_TZ


def _make_loader():
    loader = PriceLoader.__new__(PriceLoader)
    loader.table_name = "etf_price_daily"
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
    loader._bulk_insert_mgr.bulk_insert.return_value = 1
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


def _fake_db_context(max_dates_by_symbol: dict):
    # BUG FOUND 2026-09-07 (real-money-readiness audit, test-flakiness class): a later,
    # unrelated commit (90c6d300b, "block silent overwrites of already-recorded historical
    # price_daily closes") added a SECOND DatabaseContext query inside _load_batch's own
    # write path (_guard_against_historical_price_revision, a 3-column `sym, d, close`
    # SELECT). Every DatabaseContext(...) call in _load_batch shares this same factory, so
    # that second query got the SAME 2-column (symbol, MAX(date)) fetchall return value this
    # fixture was originally built for the desync-correction query alone - unpacking 2
    # values into 3 targets crashed. Route by the executed SQL's shape instead of returning
    # one fixed shape for every query on this fixture.
    def factory(mode, **kwargs):
        ctx = MagicMock()
        cur = MagicMock()

        def fake_execute(query, *args, **kwargs):
            # query is a psycopg2.sql.Composed object here, not a plain str - `in` on a
            # Composed iterates its sub-Composable parts (SQL('...'), Identifier(...)) and
            # compares each by identity/equality, so a substring check against the raw text
            # silently always returns False. str() first to get the actual rendered SQL text.
            if "MAX(date)" in str(query):
                cur.fetchall.return_value = list(max_dates_by_symbol.items())
            else:
                cur.fetchall.return_value = []

        cur.execute.side_effect = fake_execute
        ctx.__enter__.return_value = cur
        ctx.__exit__.return_value = False
        return ctx

    return factory


class TestWatermarkDesyncSelfHeal:
    def test_watermark_ahead_of_real_data_is_capped_and_symbol_gets_refetched(self):
        """The core bug: SPY's watermark claims "today" (matching the live-reproduced
        incident, where the bogus watermark exactly equalled the current date - which is
        WHY the pre-existing >2-TRADING-day-staleness deadlock-breaker never caught it, it
        doesn't look stale by that check) but the real table lags well behind. Without this
        fix, the per-symbol write-trim would discard every freshly-fetched row forever.

        BUG FOUND 2026-09-07 (real-money-readiness audit, test-flakiness class): this used to
        gap the real_max_date by 5 CALENDAR days, which is only >2 TRADING days stale when
        the 5-day window happens to span at most one weekend day - since load_prices.py's own
        staleness check was switched to trading-day-aware (2026-08-11 fix, same file), the
        deadlock-breaker legitimately does NOT fire on a run where those 5 calendar days
        contain only 1-2 trading days (e.g. today=Monday, gap=Wed-Sun), making this test's
        pass/fail depend on which real-world weekday it happened to run on. 10 calendar days
        guarantees at least 6 trading days elapsed regardless of weekend alignment, so the
        deadlock-breaker fires deterministically every day of the week.
        """
        loader = _make_loader()
        today = datetime.now(EASTERN_TZ).date()
        bogus_watermark_equal_to_today = today  # exactly matches the live incident
        real_max_date = today - timedelta(days=10)
        loader._watermark.get_watermarks_bulk.return_value = {"SPY": bogus_watermark_equal_to_today}

        fresh_row = _row("SPY", today - timedelta(days=9))

        def fake_fetch(symbols, since, **kwargs):
            # After correction, the watermark (today-10) is itself far more than 2 trading
            # days stale, so the pre-existing SESSION 297 deadlock-breaker also fires and
            # further widens the window to today-7 - composed behavior, not a value this fix
            # invents alone.
            assert since == today - timedelta(days=7), f"Expected today-7, got {since}"
            return {"SPY": [dict(fresh_row)]}

        loader.fetch_batch_incremental = MagicMock(side_effect=fake_fetch)

        with patch(
            "loaders.load_prices.DatabaseContext",
            side_effect=_fake_db_context({"SPY": real_max_date}),
        ):
            loader._load_batch(["SPY"])

        assert loader._stats["symbols_skipped_by_watermark"] == 0
        assert loader._stats["symbols_failed"] == 0
        inserted_rows = loader._bulk_insert_mgr.bulk_insert.call_args[0][0]
        assert {r["symbol"] for r in inserted_rows} == {"SPY"}

    def test_watermark_matching_real_data_is_left_untouched(self):
        """Sanity check: a healthy, in-sync watermark (like GLD/TLT's) must not be altered
        by the new correction logic itself (it may still get widened by the separate,
        pre-existing staleness deadlock-breaker if it's genuinely a few days old - that's
        unrelated, existing behavior this fix doesn't change)."""
        loader = _make_loader()
        today = datetime.now(EASTERN_TZ).date()
        good_watermark = today  # in sync AND fresh enough to avoid the deadlock-breaker too
        loader._watermark.get_watermarks_bulk.return_value = {"GLD": good_watermark}

        fresh_row = _row("GLD", today)
        loader.fetch_batch_incremental = MagicMock(return_value={"GLD": [dict(fresh_row)]})

        with patch(
            "loaders.load_prices.DatabaseContext",
            side_effect=_fake_db_context({"GLD": good_watermark}),
        ):
            loader._load_batch(["GLD"])

        loader.fetch_batch_incremental.assert_any_call(["GLD"], good_watermark)

    def test_watermark_with_zero_real_rows_falls_back_to_full_history_window(self):
        """A symbol whose watermark exists but has NO real rows at all (real_max is None)
        must be treated as needing a full re-fetch, not silently trusted."""
        loader = _make_loader()
        today = datetime.now(EASTERN_TZ).date()
        bogus_watermark = today
        loader._watermark.get_watermarks_bulk.return_value = {"GHOST": bogus_watermark}

        fresh_row = _row("GHOST", today - timedelta(days=100))
        captured = {}

        def fake_fetch(symbols, since, **kwargs):
            captured["since"] = since
            return {"GHOST": [dict(fresh_row)]}

        loader.fetch_batch_incremental = MagicMock(side_effect=fake_fetch)

        with patch(
            "loaders.load_prices.DatabaseContext",
            side_effect=_fake_db_context({}),  # no rows for GHOST at all
        ):
            loader._load_batch(["GHOST"])

        # Capped far enough back (101 days) to catch a full history re-fetch, then further
        # widened to today-7 by the pre-existing deadlock-breaker (composed behavior).
        assert captured["since"] == today - timedelta(days=7)
