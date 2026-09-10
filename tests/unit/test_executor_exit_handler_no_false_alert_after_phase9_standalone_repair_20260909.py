#!/usr/bin/env python3
"""Regression test for a false-positive CRITICAL alert on every partial exit of a
Phase-9-auto-repaired position, found via the 2026-09-09 real-money-readiness audit.

Once Phase 9 auto-repairs a position onto a STANDALONE stop, it deliberately cancels the
original bracket's stop-loss leg - but algo_trades.alpaca_order_id is never cleared, so it
stays truthy forever. The partial-exit resize block used to call _sync_bracket_stop_loss
unconditionally whenever alpaca_order_id was truthy, with no check for whether that bracket
leg was still the live protection. Since the leg is genuinely gone by design after a Phase 9
repair, this always failed and fired a real CRITICAL page (logger.critical + notify) on every
subsequent T1/T2/T3 partial exit of that position, even though the position IS fully
protected (by the standalone stop, resized correctly by the very next block).

_raise_stop_only (same file) already makes exactly this standalone-vs-bracket distinction
before choosing a sync path - fixed by mirroring that branch in the partial-exit resize guard.

Static source check, matching the established precedent for this exact function (see
test_executor_exit_handler_partial_exit_resizes_bracket_leg_20260824.py): _execute_exit has a
large dependency graph impractical to mock end-to-end.
"""

from pathlib import Path

SOURCE = (Path(__file__).parent.parent.parent / "algo" / "trading" / "executor_exit_handler.py").read_text()

_RESIZE_MARKER = "if not (full_exit or new_qty <= 0) and alpaca_order_id and not standalone_stop_order_id:"
_STANDALONE_RESIZE_MARKER = "resize_standalone_stop_after_partial_exit("


def test_bracket_resize_is_skipped_when_a_standalone_stop_is_on_file():
    assert _RESIZE_MARKER in SOURCE, (
        "the bracket-leg resize guard must require standalone_stop_order_id to be falsy - "
        "a Phase-9-repaired position (standalone stop, bracket leg deliberately cancelled) "
        "must not attempt (and false-alert on) resizing a bracket leg that no longer exists"
    )


def test_standalone_stop_order_id_fetched_once_and_reused():
    """The value used to gate the bracket-resize block must be the SAME value passed to
    resize_standalone_stop_after_partial_exit below it, not re-fetched - both reads happen
    inside the same locked transaction, so a second fetch would be redundant, not safer."""
    assert "standalone_stop_order_id = fetch_standalone_stop_order_id(cur, position_id)" in SOURCE
    resize_idx = SOURCE.index(_RESIZE_MARKER)
    standalone_call_idx = SOURCE.index(_STANDALONE_RESIZE_MARKER, resize_idx)
    standalone_call_block = SOURCE[standalone_call_idx : standalone_call_idx + 300]
    assert "standalone_stop_order_id," in standalone_call_block, (
        "resize_standalone_stop_after_partial_exit must be passed the already-fetched "
        "standalone_stop_order_id variable, not a fresh fetch_standalone_stop_order_id(...) call"
    )
    assert "fetch_standalone_stop_order_id(cur, position_id)," not in standalone_call_block, (
        "must not re-fetch standalone_stop_order_id at the call site - that duplicates the "
        "query this fix already performs once, earlier, to gate the bracket-resize block"
    )


def test_fetch_precedes_the_bracket_resize_guard():
    fetch_idx = SOURCE.index("standalone_stop_order_id = fetch_standalone_stop_order_id(cur, position_id)")
    resize_idx = SOURCE.index(_RESIZE_MARKER)
    assert fetch_idx < resize_idx, (
        "standalone_stop_order_id must be fetched BEFORE the bracket-resize guard uses it to "
        "decide whether to attempt the (now-gone, post-Phase-9-repair) bracket leg resize"
    )
