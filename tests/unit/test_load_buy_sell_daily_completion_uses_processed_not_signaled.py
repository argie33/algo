"""Regression test: buy_sell_daily's completion-threshold check must use symbols the loader
successfully PROCESSED, not symbols that happened to get an actual triggered BUY/SELL signal
on the exact latest date.

Bug (found 2026-08-10 via real DB evidence, not log-reading): _generate_signals() /
BuySignalGenerator.run() only emits a row for a symbol when a real pivot breakout (BUY) or
swing-low breakdown (SELL) fires that day - most symbols on most days trigger neither, by
design (a sparse signals table, not a full-universe daily snapshot). The completion check used
to require 95% of the effective universe to have an actual signal row on the SAME date, which
is unattainable: live data showed only 945-1000 of ~4885 symbols (~19-20%) had a row on any of
2026-08-05/06/07, so the loader marked itself FAILED on every run since 2026-08-08 despite
generating signals correctly every time. Fixed to use the loader's own per-symbol
success/failure accounting (utils/optimal_loader.py's symbols_processed counter, incremented
whether or not a symbol produced a signal - only symbols_failed reflects a real exception).
"""

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE = REPO_ROOT / "loaders" / "load_buy_sell_daily.py"


def _find_mark_completed_call():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "mark_completed"
    ]
    assert len(calls) == 1, f"Expected exactly one mark_completed() call, found {len(calls)}"
    return calls[0]


def test_completion_numerator_is_not_same_day_signal_count():
    src = SOURCE.read_text(encoding="utf-8")
    call = _find_mark_completed_call()
    numerator_kwarg = next(kw for kw in call.keywords if kw.arg == "current_run_symbols_loaded")
    numerator_expr = ast.unparse(numerator_kwarg.value)
    assert numerator_expr != "signals_symbols_generated", (
        "current_run_symbols_loaded must not be the same-day triggered-signal count - "
        "requiring 95% of the universe to breakout/breakdown on the identical date is "
        "unattainable and marks a healthy loader FAILED forever. Use the loader's own "
        "symbols_processed count from result (loader.run()'s return value) instead."
    )
    assert "signals_symbols_generated" not in numerator_expr

    # The signals-generated count may still be computed for informational logging, but must
    # not be the sole source feeding the completion gate.
    assert 'result.get("symbols_processed"' in src or "result.get('symbols_processed'" in src


def test_mark_completed_still_passes_current_run_counts():
    """Preserves the intent of the earlier 2026-08-09 fix: don't fall back to stale DB state."""
    call = _find_mark_completed_call()
    kwarg_names = {kw.arg for kw in call.keywords}
    assert "current_run_symbols_loaded" in kwarg_names
    assert "current_run_symbol_count" in kwarg_names
