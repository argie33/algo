"""Regression test: a symbol whose fetched rows were ALL quality-rejected before the write-trim
step must be counted as a real failure, not credited as a benign "already loaded" watermark skip.

See [[load_prices_symbols_failed_silently_swallowed_fixed_20260823]] in memory. `_load_batch()`'s
WRITE TRIM block trims rows already covered by a symbol's own watermark. Before the fix, `if not
rows:` alone gated the benign-skip branch - true both when trimming genuinely removed pre-existing
rows (real watermark-current case) AND when `rows` was already empty walking in (e.g. every
fetched row was rejected by the quality validator a few lines up). Both cases credited
`symbols_skipped_by_watermark`, making the real failure-counting block below permanently
unreachable for any symbol with an existing watermark - i.e. every actively-tracked symbol,
always. Live-confirmed: CDTG/IPST/LGCL/MDV had 66-100% of fetched rows quality-rejected daily for
over a week with zero visible failure in symbols_failed, loader_watermarks.error_count, or
data_loader_status.

Fixed by requiring `before_trim > 0` (trimming actually removed rows that existed) for the
benign-skip branch, so an already-empty `rows` list falls through to the real `if not rows:`
failure-counting block instead.

Like test_phase8_min_entry_price_gate_wired_and_audited.py / test_sizer_blocked_and_liquidity_
skips_are_persisted_to_audit_table in test_phase8_execution_failure_audit_gap.py, this is a
source-inspection test: `_load_batch()` is heavily DB-coupled (fetch, transform, bulk insert,
watermark writes all inline in one method) with no existing mock harness for the whole method,
so pinning the exact condition shape is this codebase's established way of guarding logic this
deep without building that harness from scratch.
"""

import inspect

from loaders.load_prices import PriceLoader


def test_benign_skip_branch_requires_trim_to_have_actually_removed_rows() -> None:
    source = inspect.getsource(PriceLoader._load_batch)

    # The benign "already loaded, watermark current" skip must require before_trim > 0 -
    # i.e. trimming actually removed rows that existed pre-trim - not just `if not rows:`
    # alone, which is also true when nothing survived quality validation in the first place.
    assert "if not rows and before_trim > 0:" in source


def test_zero_input_rows_falls_through_to_the_real_failure_branch() -> None:
    """The benign-skip branch must `continue` before reaching the failure-counting block, so
    the two are mutually exclusive for a single iteration - confirms the fallthrough for
    before_trim == 0 actually reaches `symbols_failed += 1` rather than being caught twice."""
    source = inspect.getsource(PriceLoader._load_batch)

    benign_skip_branch = source.split("if not rows and before_trim > 0:")[1].split("continue", 1)[0]
    assert '_stats["symbols_skipped_by_watermark"] += 1' in benign_skip_branch
    assert "continue" not in benign_skip_branch.split('_stats["symbols_skipped_by_watermark"]')[0]

    # After the (possibly skipped) benign branch, the real failure branch must still be the
    # very next `if not rows:` CODE line (not the same phrase's mentions inside comments
    # above it) - i.e. nothing re-guards it into unreachability again.
    after_benign_skip = source.split("if not rows and before_trim > 0:")[1]
    failure_branch = after_benign_skip.split("\n            if not rows:\n")[1].split("continue", 1)[0]
    assert '_stats["symbols_failed"] += 1' in failure_branch
