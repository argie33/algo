"""Regression test: a symbol whose fetch returns only already-loaded overlap/cross-check rows
(zero real progress) must be counted as a real failure, not silently credited as a success.

See [[price_daily_frozen_yfinance_fallback_193_symbols_20260913]] in memory. `_load_batch()`'s
WRITE TRIM block deliberately keeps a 1-day overlap window around a symbol's own watermark for
cross-checking. When a symbol's primary source (Alpaca) has a genuine external gap and its
yfinance residual fallback returns nothing but flat/zero-volume placeholder rows (rejected by
`_validate_row`), the only rows that survive validation+trim are those pre-existing overlap
rows - `rows` is non-empty, so it skips both the benign "trim removed rows" branch and the
`if not rows:` failure branch, and falls straight into the success path:
`watermark_from_rows(rows)` computes the SAME date as the existing watermark (zero real
progress), yet `advance_watermarks_bulk()` resets `error_count` to 0 and bumps
`last_run_at`/`last_success_at` every single day. Live-confirmed on EA/WBS: `loader_watermarks`
showed `error_count=0`, `rows_loaded=2`, watermark stuck 24-40 days behind, running
"successfully" every day forever.

Fixed by comparing the computed new watermark against the symbol's existing one: if it doesn't
advance and the existing watermark is already stale (past the same `stale_threshold` used
elsewhere in this method), route it through the same failure-counting path as an empty fetch
instead of the success path.

Same source-inspection testing approach as its sibling
test_load_prices_write_trim_zero_input_counts_as_failure.py - `_load_batch()` is heavily
DB-coupled with no existing mock harness for the whole method.
"""

import inspect

from loaders.load_prices import PriceLoader


def test_non_advancing_watermark_is_detected_before_success_path() -> None:
    source = inspect.getsource(PriceLoader._load_batch)

    assert "new_watermark = self.watermark_from_rows(rows)" in source
    assert "if sym_wm is not None and new_watermark <= sym_wm:" in source


def test_stalled_watermark_falls_through_to_failure_branch_not_success() -> None:
    source = inspect.getsource(PriceLoader._load_batch)

    stall_branch = source.split("if sym_wm is not None and new_watermark <= sym_wm:")[1]
    stall_branch = stall_branch.split("# Stage this symbol's rows")[0]

    assert '_stats["symbols_failed"] += 1' in stall_branch
    assert "continue" in stall_branch
    # The stall check must run BEFORE pending_watermarks is populated for this symbol, so a
    # stalled symbol can never reach advance_watermarks_bulk() (the false-success path).
    assert "pending_watermarks[symbol]" not in stall_branch


def test_success_path_reuses_the_precomputed_new_watermark() -> None:
    """pending_watermarks must use the same `new_watermark` value the stall check already
    validated, not a second independent call to watermark_from_rows(rows) that could compute
    a different result if `rows` were mutated in between."""
    source = inspect.getsource(PriceLoader._load_batch)

    assert "pending_watermarks[symbol] = (new_watermark, len(rows))" in source
