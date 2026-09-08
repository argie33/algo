#!/usr/bin/env python3
"""Regression test: exit_engine.py's core exit-candidate query must resolve entry_price
from the position's blended avg_entry_price and must match exactly ONE algo_trades row
per position, not join on ANY(trade_ids_arr).

Bug (2026-09-07 real-money-readiness audit, 4th independent copy of the pyramided-
position entry-price bug class - see the P&L fixes in executor_exit_handler.py's
_fetch_and_lock_trade_data/_compute_cumulative_pnl and phase9_reconciliation.py's
_record_closed_positions_exits). This query previously joined
`t.trade_id::text = ANY(p.trade_ids_arr::text[])` and selected `t.entry_price` directly:

1. A position with 2+ entries in trade_ids_arr (a pyramid add) would match MULTIPLE
   algo_trades rows, so the same position would be evaluated for exit/trailing-stop-raise
   once per leg per cycle instead of once - each time anchored to a DIFFERENT leg's own
   entry_price, not the position's actual blended cost basis.
2. Even for a single matched row, t.entry_price is that one trade's own fill price, not
   the position's blended avg_entry_price - so trailing-stop-raise/lock-in-gain logic
   (_evaluate_position, _check_stop_loss_hit) would anchor to the wrong cost basis for a
   pyramided position.

Fix: match only trade_ids_arr[1] (the array's first/original trade - the same convention
every other consumer uses: phase9_stop_loss_repair.py, phase6_exit_execution.py,
position_monitor.py all resolve trade_id = trade_ids_arr[0]), and select
COALESCE(p.avg_entry_price, t.entry_price) so a pyramided position's blended cost basis
feeds the stop/gain math, matching the pattern already used by
test_executor_exit_handler_pyramided_entry_price_20260907.py for the exit-execution path.
"""

from datetime import date
from unittest.mock import MagicMock, patch

from algo.trading.exit_engine import ExitEngine


def _mock_config():
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
        "use_scale_out_targets": True,
        "execution_mode": "paper",
        "alpaca_paper_trading": True,
        "t1_target_r_multiple": 1.5,
        "t2_target_r_multiple": 3.0,
        "t3_target_r_multiple": 4.0,
        "max_reentries_per_name": 2,
        "min_days_before_reentry_same_symbol": 5,
        "wash_sale_cooldown_days": 31,
    }


def test_candidate_query_uses_coalesced_blended_entry_price_and_first_leg_join():
    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = []

    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_cur
    mock_ctx.__exit__.return_value = False

    with patch("algo.trading.exit_engine.TradeExecutor"):
        engine = ExitEngine(_mock_config())
        with patch("algo.trading.exit_engine.DatabaseContext", return_value=mock_ctx):
            engine.check_and_execute_exits(date(2026, 9, 7))

    executed_sql = None
    for call in mock_cur.execute.call_args_list:
        sql = call[0][0]
        if "FROM algo_trades t" in sql and "JOIN algo_positions p" in sql:
            executed_sql = sql
            break

    assert executed_sql is not None, "candidate-selection query not found among executed statements"
    assert "COALESCE(p.avg_entry_price, t.entry_price)" in executed_sql
    assert "p.trade_ids_arr[1]" in executed_sql
    assert "ANY(p.trade_ids_arr" not in executed_sql
