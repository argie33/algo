#!/usr/bin/env python3
"""Regression test: ExitEngine.check_and_execute_exits() must persist per-trade exit-check
failures to algo_exit_check_errors, not just logger.error() them.

Background: the per-trade loop wraps each position in a SAVEPOINT and, on any unrecognized
exception, rolls back and logs "Exit check failed for X" then moves on - previously that log
line was the ONLY record of the failure anywhere. For scheduled/background orchestrator runs
(virtually all of them) that stdout is gone the moment the process exits, so a run reporting
"N errors" gave zero forensic detail after the fact (confirmed live: run
LOCAL-MORNING-20260727-112904-608395 had "7 errors" with no way to determine which positions
or why). Mirrors the existing algo_signal_rejections audit pattern for Phase 8 entry
rejections, applied to exit-check failures.
"""

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import pytest

from algo.trading.exit_engine import ExitEngine


@pytest.fixture
def mock_config():
    return {
        "min_hold_days": 1,
        "max_hold_days": 60,
        "eight_week_rule_threshold_pct": 20.0,
        "eight_week_rule_window_days": 21,
        "exit_on_distribution_day": False,
        "max_distribution_days": 3,
        "move_be_at_r": 1.0,
        "chandelier_atr_mult": 3.0,
        "use_chandelier_trail": False,
        "exit_on_td_sequential": False,
        "exit_on_rs_line_break_50dma": False,
        "require_target_pullback": True,
        "execution_mode": "paper",
        "alpaca_paper_trading": True,
    }


def _trade_row(trade_id="TRD-1", symbol="BADSYM", position_id="POS-1"):
    trade_date = date(2026, 7, 22) - timedelta(days=5)
    return (
        trade_id,
        symbol,
        100.0,
        90.0,
        None,
        None,
        None,
        trade_date,
        position_id,
        10,
        0,
        90.0,
        None,
        None,
        None,
        None,
        None,
    )


def test_trade_error_is_persisted_to_audit_table(mock_config):
    current_date = date(2026, 7, 22)
    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = [_trade_row()]
    mock_cur.fetchone.return_value = ("open", 10, 90.0)

    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_cur
    mock_ctx.__exit__.return_value = False

    with patch("algo.trading.exit_engine.TradeExecutor"):
        engine = ExitEngine(mock_config)
        with (
            patch("algo.trading.exit_engine.DatabaseContext", return_value=mock_ctx),
            patch.object(engine, "_fetch_market_dist_days", return_value=set()),
            patch.object(engine, "_fetch_recent_prices", return_value=(105.0, 100.0)),
            patch.object(
                engine,
                "_evaluate_position",
                side_effect=RuntimeError("simulated unexpected evaluation failure"),
            ),
        ):
            exits_executed, stop_raises_executed, trade_errors = engine.check_and_execute_exits(current_date)

    assert trade_errors == 1

    insert_calls = [c for c in mock_cur.execute.call_args_list if "INSERT INTO algo_exit_check_errors" in str(c)]
    assert len(insert_calls) == 1, "trade error must be persisted to algo_exit_check_errors"
    args = insert_calls[0].args[1]
    assert args[0] == current_date
    assert args[1] == "TRD-1"
    assert args[2] == "POS-1"
    assert args[3] == "BADSYM"
    assert args[4] == "RuntimeError"
    assert "simulated unexpected evaluation failure" in args[5]

    # Audit insert must be wrapped in its own savepoint (released on success)
    audit_savepoints = [c for c in mock_cur.execute.call_args_list if "_audit" in str(c)]
    assert any("SAVEPOINT" in str(c) for c in audit_savepoints)
    assert any("RELEASE SAVEPOINT" in str(c) for c in audit_savepoints)


def test_audit_insert_failure_does_not_crash_the_run(mock_config):
    """If the audit table itself is unavailable, exit-check coverage for the REST of the
    batch must not be lost - the audit insert failure has to be swallowed after rolling
    back to its own savepoint, not left to abort the whole outer transaction."""
    current_date = date(2026, 7, 22)
    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = [_trade_row(trade_id="TRD-1", symbol="SYM1", position_id="POS-1")]
    mock_cur.fetchone.return_value = ("open", 10, 90.0)

    def execute_side_effect(sql, *args, **kwargs):
        if "INSERT INTO algo_exit_check_errors" in sql:
            raise RuntimeError("audit table unavailable")

    mock_cur.execute.side_effect = execute_side_effect

    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_cur
    mock_ctx.__exit__.return_value = False

    with patch("algo.trading.exit_engine.TradeExecutor"):
        engine = ExitEngine(mock_config)
        with (
            patch("algo.trading.exit_engine.DatabaseContext", return_value=mock_ctx),
            patch.object(engine, "_fetch_market_dist_days", return_value=set()),
            patch.object(engine, "_fetch_recent_prices", return_value=(105.0, 100.0)),
            patch.object(
                engine,
                "_evaluate_position",
                side_effect=RuntimeError("simulated unexpected evaluation failure"),
            ),
        ):
            # Must not raise despite the audit insert itself failing.
            exits_executed, stop_raises_executed, trade_errors = engine.check_and_execute_exits(current_date)

    assert trade_errors == 1
    rollback_calls = [c for c in mock_cur.execute.call_args_list if "ROLLBACK TO SAVEPOINT" in str(c)]
    # One rollback for the trade's own savepoint, one for the failed audit-insert savepoint
    assert len(rollback_calls) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
