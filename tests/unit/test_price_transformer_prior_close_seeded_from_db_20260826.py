#!/usr/bin/env python3
"""Regression tests: a normal, single-row-per-symbol daily incremental load must still be
checked against the symbol's REAL last known state already in price_daily, not skip the
30%-gap/split-detection sequence check or the duplicate-OHLC check entirely.

BUG FOUND 2026-08-26 (real-money-readiness review): prior_close_by_symbol (and, once added,
prior_ohlc_by_symbol) started as empty dicts on every call to validate_and_transform().
TickValidator._check_sequence no-ops when prior_close is falsy, and _check_duplicate no-ops
when prior_ohlc is None - so the FIRST row seen for a symbol in a batch was never checked
against either rule. A normal daily incremental load passes exactly one row per symbol, so
that row was ALWAYS the "first" row - meaning both safety checks had been silently disabled
for the routine, everyday ingestion path since they were written, only ever engaging within a
multi-row backfill batch.

Sequence check: live-confirmed via a self-reverting single-day price spike/dip signature
(close jumps >8x from the day before AND reverts >8x by the day after) affecting 553 rows
across 261 distinct symbols in just the last 2 years of price_daily alone.

Duplicate check: live-confirmed via 770 rows across 243 distinct symbols (2025+) where
open/high/low/close ALL exactly match the prior trading day's values while claiming
substantial, DIFFERENT real trading volume on both days - a 0% close-to-close gap (so the
sequence check never engages), essentially impossible for two genuinely independent trading
sessions. See [[price_daily_duplicate_stale_quote_check_implemented_20260826]].

Fixed by loaders/price_transformer.py::PriceTransformer._seed_prior_state(), called at the
start of validate_and_transform() to seed prior_close_by_symbol AND prior_ohlc_by_symbol from
price_daily's last known-good row strictly before the batch's earliest date.

Mocks _seed_prior_state directly rather than hitting a real DB: tests/conftest.py points
DatabaseContext at algo_trading (near-empty, pytest-only - see CLAUDE.md/memory
feedback_always_use_pipeline_scheduler_for_backfills), not the real local dev `stocks` DB
this fix's own live-verification queries ran against, so an unmocked test here would silently
degrade to "no seed found" (the pre-fix behavior) rather than actually exercising the fix.
"""

from unittest.mock import patch

from loaders.price_transformer import PriceTransformer


def _seeded(prior_close: float, prior_ohlc: tuple[float, float, float, float]):
    return patch.object(
        PriceTransformer,
        "_seed_prior_state",
        return_value=({"AAPL": prior_close}, {"AAPL": prior_ohlc}),
    )


class TestPriorCloseSeededFromRealHistory:
    def test_single_row_batch_rejects_extreme_unexplained_jump_vs_seeded_history(self):
        """A single incoming row (the normal shape of a daily incremental load: one row per
        symbol) with a +61% jump vs. a seeded prior close, not matching any clean split
        ratio, must be rejected - this is exactly the case the pre-fix empty dict silently
        never protected, since it was always this call's "first" row for the symbol."""
        transformer = PriceTransformer(asset_class="stock")

        rows = [
            {
                "symbol": "AAPL",
                "date": "2026-08-26",
                "open": 495.0,
                "high": 505.0,
                "low": 490.0,
                "close": 500.0,
                "volume": 50000000,
            },
        ]

        with _seeded(309.9, (309.0, 312.0, 307.0, 309.9)):
            valid_rows = transformer.validate_and_transform(rows)

        assert valid_rows == [], (
            "a single-row batch must still be validated against the seeded real prior "
            "close, not silently accepted because it's the first row this call has seen"
        )

    def test_single_row_batch_accepts_a_normal_move_vs_seeded_history(self):
        """Sanity check the fix isn't over-rejecting: a plausible day-over-day move vs. a
        seeded prior close must still pass."""
        transformer = PriceTransformer(asset_class="stock")

        rows = [
            {
                "symbol": "AAPL",
                "date": "2026-08-26",
                "open": 310.5,
                "high": 314.0,
                "low": 308.0,
                "close": 313.2,
                "volume": 45000000,
            },
        ]

        with _seeded(309.9, (309.0, 312.0, 307.0, 309.9)):
            valid_rows = transformer.validate_and_transform(rows)

        assert len(valid_rows) == 1
        assert valid_rows[0]["close"] == 313.2

    def test_seed_query_failure_degrades_to_pre_fix_behavior_not_a_hard_failure(self):
        """_seed_prior_state is best-effort: if the seeding query itself fails (DB error),
        price ingestion must not be blocked entirely - it falls back to empty dicts, the
        same behavior as before this fix, rather than raising."""
        transformer = PriceTransformer(asset_class="stock")

        rows = [
            {
                "symbol": "AAPL",
                "date": "2026-08-26",
                "open": 495.0,
                "high": 505.0,
                "low": 490.0,
                "close": 500.0,
                "volume": 50000000,
            },
        ]

        with patch(
            "utils.db.context.DatabaseContext",
            side_effect=RuntimeError("simulated DB outage"),
        ):
            valid_rows = transformer.validate_and_transform(rows)

        assert len(valid_rows) == 1, (
            "a seeding failure must degrade gracefully (no seed = pre-fix behavior), not block price ingestion entirely"
        )


class TestDuplicateOhlcSeededFromRealHistory:
    def test_single_row_batch_rejects_identical_ohlc_with_real_volume(self):
        """A single incoming row with OHLC EXACTLY equal to the seeded prior day's OHLC,
        claiming real (and different) trading volume, must be rejected - the live-confirmed
        stale/duplicate-quote pattern (770 rows/243 symbols, 2025+)."""
        transformer = PriceTransformer(asset_class="stock")

        rows = [
            {
                "symbol": "AAPL",
                "date": "2026-08-26",
                "open": 309.0,
                "high": 312.0,
                "low": 307.0,
                "close": 309.9,
                "volume": 40000000,  # different from the seeded prior day's volume, real activity claimed
            },
        ]

        with _seeded(309.9, (309.0, 312.0, 307.0, 309.9)):
            valid_rows = transformer.validate_and_transform(rows)

        assert valid_rows == [], (
            "identical OHLC to the prior day with real claimed volume must be rejected as a "
            "suspected stale/duplicate quote, not silently accepted because it's the first "
            "row this call has seen"
        )

    def test_zero_volume_duplicate_is_not_rejected_by_the_duplicate_check(self):
        """A genuinely illiquid symbol with no new trades can legitimately carry its last
        price forward - the duplicate check requires real claimed volume (> 0) specifically
        so it doesn't reject this legitimate case."""
        transformer = PriceTransformer(asset_class="stock")

        rows = [
            {
                "symbol": "AAPL",
                "date": "2026-08-26",
                "open": 309.0,
                "high": 312.0,
                "low": 307.0,
                "close": 309.9,
                "volume": 0,
            },
        ]

        with _seeded(309.9, (309.0, 312.0, 307.0, 309.9)):
            valid_rows = transformer.validate_and_transform(rows)

        assert len(valid_rows) == 1
