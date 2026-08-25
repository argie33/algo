"""Regression/documentation test for a 2026-08-25 finding (real-money-readiness goal
session - checked whether any trade-creation path bypasses pretrade_checks.py's sector/
industry/correlation/beta risk gates): lambda/api/routes/trades.py's admin-gated
POST /api/trades/manual endpoint is the only other real "INSERT INTO algo_trades" site in
the codebase besides the audited algorithmic entry path
(executor_entry_handler.py/executor.py/phase8_entry_execution.py).

This is intentional, not a bug: it records a trade that already happened externally
(outside the algo), so there is nothing left to approve or reject via pretrade_checks. But
it also never inserts into algo_positions, so those position-based risk checks (and
position_sizer.py's exposure accounting) do not see a manually-recorded trade until
algo/orchestration/position_sync.py's sync_positions_from_trades() next runs (before every
Phase 1, 4-5x/day in production) - a bounded eventual-consistency window, not an instant
one.

This test pins that characteristic explicitly (via source inspection, not by exercising the
real endpoint - it requires a live DB/auth context this test suite doesn't set up) so a
future change that makes this endpoint touch algo_positions directly - a legitimate future
improvement - is a deliberate, reviewed decision rather than an accidental behavior change
this test would otherwise silently stop describing correctly.
"""

import importlib
import inspect

# 'lambda' is a Python keyword, so lambda/api modules are loaded via importlib - matches
# test_request_models_reject_nan_prices.py's established approach for this same directory.
trades = importlib.import_module("lambda.api.routes.trades")


def test_create_manual_trade_is_gated_behind_admin_access():
    handle_source = inspect.getsource(trades.handle)
    # Every branch that can reach _create_manual_trade must be preceded by an admin check
    # in the same handler - confirmed by presence of both symbols in the function source
    # (the exact call-order is already covered by this file's real routing logic; this test
    # guards against the check being removed entirely, not exact placement).
    assert "check_admin_access" in handle_source
    assert "_create_manual_trade" in handle_source


def test_create_manual_trade_does_not_touch_algo_positions():
    """Documents the bounded eventual-consistency gap: this function only inserts into
    algo_trades, never algo_positions. If this now fails, the endpoint has been changed to
    touch algo_positions directly - update this test's docstring and the matching comment in
    lambda/api/routes/trades.py to reflect the new (improved) reality rather than deleting
    this test outright."""
    source = inspect.getsource(trades._create_manual_trade)
    assert "INSERT INTO algo_trades" in source
    assert "algo_positions" not in source.split('"""', 2)[-1], (
        "found an 'algo_positions' reference outside this function's own docstring - "
        "if this endpoint now writes to algo_positions directly, that's a real "
        "improvement: update this test and the matching comment in trades.py to describe "
        "the new (better) reality instead of leaving this assertion silently stale."
    )


def test_create_manual_trade_does_not_call_pretrade_checks():
    """Confirms the deliberate design: recording an already-completed external trade has
    nothing left to approve/reject, so pretrade_checks.py's risk gates are correctly not
    invoked here (unlike the real algorithmic entry path)."""
    source = inspect.getsource(trades._create_manual_trade)
    assert "PreTradeChecks" not in source
    assert "run_all(" not in source
