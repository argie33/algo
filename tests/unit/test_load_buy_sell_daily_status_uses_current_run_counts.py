"""Regression test: load_buy_sell_daily.py's mark_completed() call must pass this
run's own verified symbol counts, not rely on stale DB state.

Bug (fixed 2026-08-09): this loader never called update_progress() during its run and
never passed current_run_symbols_loaded/current_run_symbol_count to mark_completed().
Per utils/loaders/status_manager.py's own documented "etf_price_daily" bug, callers that
omit these two params get their completion-percentage safety check computed against
whatever symbol_count/symbols_loaded a PAST run last wrote to the data_loader_status row
- frozen forever if this loader (which also never calls update_progress()) never updates
them itself. Live-reproduced 2026-08-09: data_loader_status showed a static
"4591/4863 (94.41%)" for buy_sell_daily across 14 consecutive runs regardless of actual
outcome. Fixed by passing the already-computed effective-universe coverage numbers
(signals_symbols_generated / effective_universe) that this same code block already used
for its own log line.
"""

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE = REPO_ROOT / "loaders" / "load_buy_sell_daily.py"


def _find_mark_completed_call():
    """Returns the main (real-data) mark_completed() call - the one carrying
    current_run_symbols_loaded. A second call exists for the zero-data-day branch (e.g. a
    weekend/holiday with no new signals - see the "zero-data day" comment in
    load_buy_sell_daily.py), which intentionally omits these kwargs since there's no
    per-run count to report; that call isn't what this test is verifying."""
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "mark_completed"
    ]
    assert calls, "Expected at least one mark_completed() call, found none"
    main_calls = [call for call in calls if any(kw.arg == "current_run_symbols_loaded" for kw in call.keywords)]
    assert len(main_calls) == 1, (
        f"Expected exactly one mark_completed() call passing current_run_symbols_loaded, "
        f"found {len(main_calls)} (of {len(calls)} total mark_completed() calls)"
    )
    return main_calls[0]


def test_mark_completed_passes_current_run_counts():
    call = _find_mark_completed_call()
    kwarg_names = {kw.arg for kw in call.keywords}
    assert "current_run_symbols_loaded" in kwarg_names, (
        "mark_completed() must pass current_run_symbols_loaded so the completion-pct "
        "safety check reflects this run, not a stale DB value from a past run"
    )
    assert "current_run_symbol_count" in kwarg_names, (
        "mark_completed() must pass current_run_symbol_count so the completion-pct "
        "safety check reflects this run, not a stale DB value from a past run"
    )
