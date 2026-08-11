#!/usr/bin/env python3
"""Regression test for the 2026-07-27 fix: check_and_execute_exits() folded stop-raise-only
outcomes (fraction=0 - no shares sold, just a tighter stop) into the same exits_executed
counter as actual position exits (fraction>0). phase6_exit_execution.py adds exits_executed
straight into its own "N exits" total, while tracking "M stop-raises" from a completely
unrelated source (Phase 3 recommendations) - so a run where every open position just got a
routine trailing-stop tighten, and none actually closed, could report "16 exits, 0
stop-raises". Live-reproduced 2026-07-27: a clean orchestrator run reported "16 exits,
0 stop-raises, 0 errors" in its Phase 6 summary, yet all 16 pre-existing positions were
still open at their original quantity immediately afterward.

check_and_execute_exits() must now return (exits_executed, stop_raises_executed,
trade_errors) with stop-raise-only outcomes counted separately, not folded into exits.
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


def test_stop_raise_only_outcome_is_not_counted_as_an_exit(mock_config):
    """A fraction=0 (stop-raise-only) exit_signal must increment stop_raises_executed,
    not exits_executed - the position stays open, no shares were sold."""
    current_date = date(2026, 7, 22)
    trade_date = current_date - timedelta(days=5)

    trade_row = (
        "TRD-1",  # trade_id
        "WINNER",  # symbol
        100.0,  # entry_price
        90.0,  # stop_loss_price
        None,
        None,
        None,  # t1/t2/t3 price
        trade_date,
        "POS-1",  # position_id
        10,  # quantity
        0,  # target_levels_hit
        95.0,  # current_stop_price
        None,
        None,
        None,  # t1/t2/t3 hit times
        None,  # last_partial_exit_date
        None,  # partial_exits_log
    )

    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = [trade_row]
    # FOR UPDATE re-fetch of position status: still open, same quantity/stop
    mock_cur.fetchone.return_value = ("open", 10, 95.0)

    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_cur
    mock_ctx.__exit__.return_value = False

    stop_raise_signal = {"fraction": 0, "stage": "trail", "reason": "trailing stop tighten", "new_stop": 98.0}

    with patch("algo.trading.exit_engine.TradeExecutor"):
        engine = ExitEngine(mock_config)
        engine.executor.exit_trade = MagicMock(return_value={"success": True, "message": "stop raised"})

        with (
            patch("algo.trading.exit_engine.DatabaseContext", return_value=mock_ctx),
            patch.object(engine, "_fetch_market_dist_days", return_value=set()),
            patch.object(engine, "_fetch_recent_prices", return_value=(105.0, 100.0)),
            patch.object(engine, "_evaluate_position", return_value=stop_raise_signal),
        ):
            exits_executed, stop_raises_executed, trade_errors, _forced_closes_no_price = (
                engine.check_and_execute_exits(current_date)
            )

    assert (exits_executed, stop_raises_executed, trade_errors) == (0, 1, 0), (
        "a stop-raise-only outcome must be counted in stop_raises_executed, not "
        "exits_executed - the position was not closed"
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
