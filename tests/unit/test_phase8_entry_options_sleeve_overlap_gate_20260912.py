"""Regression tests for the options-sleeve equity-overlap gate added 2026-09-12.

steering/OPTIONS_STRATEGY_SPEC.md section 6 is a hard rule: the options sleeve and the equity
strategy must never both hold exposure to the same underlying. Phase 4
(algo/risk/options_collateral.py's has_equity_overlap()) only enforced the sleeve-entering-
checks-equity direction (called from circuit_breaker_options.py before a CSP entry). This
closes the other direction: run()'s pre-entry concentration-prefilter loop
(phase8_entry_execution.py) now calls the same has_equity_overlap() before the equity strategy
opens a new position, skipping any symbol the sleeve already has open/assigned exposure to.

Reuses the Phase8Deps/_FakeCursor harness from test_phase8_run_core_loop_integration_20260831.py
rather than rebuilding it - see that file's own docstring for why this harness exists.
"""

from unittest.mock import patch

from algo.orchestrator.phase8_entry_execution import run
from tests.unit.test_phase8_run_core_loop_integration_20260831 import (
    Phase8Deps,
    _FakeCursor,
    _make_signal,
    _run_kwargs,
)


def _cursor_with_sleeve_overlap(base_cursor: _FakeCursor, overlapping_symbols: set) -> None:
    """Patches fetchone() so the has_equity_overlap() sleeve-position query reports an open
    algo_options_positions row for any symbol in `overlapping_symbols`, everything else
    answered by the harness's normal defaults."""
    real_fetchone = _FakeCursor.fetchone

    def _fetchone():
        sql = base_cursor._last_sql.upper()
        if "ALGO_OPTIONS_POSITIONS" in sql:
            params = base_cursor.executed[-1][1]
            symbol = params[0] if params else None
            if symbol in overlapping_symbols:
                return (1,)
            return None
        return real_fetchone(base_cursor)

    base_cursor.fetchone = _fetchone


def test_candidate_with_open_sleeve_position_is_skipped():
    """A symbol with an open/assigned options-sleeve position never reaches TradeExecutor,
    but a same-batch candidate with no sleeve exposure still can."""
    overlapping = _make_signal("AAPL", composite_score=90.0)
    clean = _make_signal("MSFT", composite_score=80.0)
    executor_result = {"success": True, "trade_id": 1, "alpaca_order_id": "o1", "status": "filled"}

    with Phase8Deps(executor_result=executor_result) as deps:
        _cursor_with_sleeve_overlap(deps.fake_cursor, {"AAPL"})
        with patch("algo.orchestrator.phase8_entry_execution._log_signal_rejection") as mock_log_rejection:
            result = run(**_run_kwargs([overlapping, clean]))

    assert deps.mock_trade_executor.execute_trade.call_count == 1
    assert deps.mock_trade_executor.execute_trade.call_args.kwargs["symbol"] == "MSFT"
    assert result.data["entered"] == 1

    overlap_rejections = [c for c in mock_log_rejection.call_args_list if "options_sleeve_overlap" in c.args[2]]
    assert len(overlap_rejections) == 1
    assert overlap_rejections[0].args[0] == "AAPL"


def test_candidate_with_no_sleeve_position_is_admitted():
    """No open sleeve exposure anywhere -> the gate is a no-op, candidate proceeds normally."""
    clean = _make_signal("AAPL")
    executor_result = {"success": True, "trade_id": 1, "alpaca_order_id": "o1", "status": "filled"}

    with Phase8Deps(executor_result=executor_result) as deps:
        result = run(**_run_kwargs([clean]))

    assert deps.mock_trade_executor.execute_trade.call_count == 1
    assert result.data["entered"] == 1


def test_overlap_check_error_fails_closed():
    """has_equity_overlap() raising (e.g. a DB error) skips the candidate rather than letting
    it proceed unchecked - this is a hard capital-safety rule, not a diversification
    preference, so it must fail closed like the duplicate-entry-today check above it, not open
    like the sector-concentration gate."""
    signal = _make_signal("AAPL")
    executor_result = {"success": True, "trade_id": 1, "alpaca_order_id": "o1", "status": "filled"}

    with Phase8Deps(executor_result=executor_result) as deps:
        with patch(
            "algo.orchestrator.phase8_guards.has_equity_overlap",
            side_effect=RuntimeError("db unavailable"),
        ):
            with patch("algo.orchestrator.phase8_entry_execution._log_signal_rejection") as mock_log_rejection:
                result = run(**_run_kwargs([signal]))

    assert deps.mock_trade_executor.execute_trade.call_count == 0
    assert result.data["entered"] == 0
    error_rejections = [c for c in mock_log_rejection.call_args_list if "sleeve_overlap_check_error" in c.args[2]]
    assert len(error_rejections) == 1
