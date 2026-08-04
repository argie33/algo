"""Regression test: loaders/compute_circuit_breakers.py's _compute_consecutive_losses,
_compute_win_rate, _compute_daily_loss, and _compute_weekly_loss must agree with the live
trading gate (algo/risk/circuit_breaker.py) they're meant to mirror for the dashboard.

Before this fix:
- _compute_consecutive_losses used a plain query with no exclusions and no exit_time
  tiebreak, so it kept counting bug-induced closes (marked DATA-QC after the live gate was
  fixed) as real losses. Live-reproduced 2026-07-27: circuit_breaker_status showed
  consecutive_losses=10 (CB3 triggered) for hours after the live gate correctly reported 0.
- _compute_win_rate had the same missing-exclusions bug plus didn't include open
  positions' unrealized P&L like the live win_rate_floor check does. Live-reproduced
  2026-07-27: reported 40.0% while the live gate reported the real 61.1%.
- _compute_daily_loss/_compute_weekly_loss used the raw (non-cash-flow-adjusted)
  total_portfolio_value/daily_return_pct columns instead of adjusted_equity, the same bug
  class _compute_drawdown was already fixed for (migration 1134). Live-reproduced
  2026-07-27: values disagreed with the live gate whenever there was any capital flow.
"""

import importlib
from datetime import date
from unittest.mock import MagicMock

module = importlib.import_module("loaders.compute_circuit_breakers")


def test_consecutive_losses_query_excludes_non_representative_closes():
    cur = MagicMock()
    cur.fetchall.return_value = []
    module._compute_consecutive_losses(cur)

    sql = cur.execute.call_args[0][0]
    params = cur.execute.call_args[0][1]

    assert "EXT-%%" in sql
    assert "exit_time DESC NULLS LAST" in sql
    assert params == ("%reconciliation%", "%force%close%", "%delisted%", "%DATA-QC%", "%CONCENTRATION%")


def test_consecutive_losses_skips_null_pnl_and_stops_at_first_win():
    cur = MagicMock()
    cur.fetchall.return_value = [
        {"profit_loss_pct": -1.0},
        {"profit_loss_pct": None},
        {"profit_loss_pct": -2.0},
        {"profit_loss_pct": 0.5},
        {"profit_loss_pct": -3.0},
    ]
    assert module._compute_consecutive_losses(cur) == 2


def test_consecutive_losses_returns_zero_for_no_closed_trades():
    cur = MagicMock()
    cur.fetchall.return_value = []
    assert module._compute_consecutive_losses(cur) == 0


def test_win_rate_query_excludes_non_representative_closes_and_includes_open_positions():
    cur = MagicMock()
    cur.fetchone.return_value = {"wins": 1, "losses": 1}
    module._compute_win_rate(cur)

    sql = cur.execute.call_args[0][0]
    params = cur.execute.call_args[0][1]

    assert "EXT-%%" in sql
    assert "exit_r_multiple IS NOT NULL" in sql
    assert "unrealized_pnl_pct" in sql
    assert "status = 'open'" in sql
    assert params == ("%reconciliation%", "%force%close%", "%delisted%", "%DATA-QC%", "%CONCENTRATION%")


def test_daily_loss_uses_adjusted_equity_not_raw_return_column():
    cur = MagicMock()
    cur.fetchone.side_effect = [
        {"adjusted_equity": 99000.0},
        {"adjusted_equity": 100000.0},
    ]
    loss = module._compute_daily_loss(cur, date(2026, 7, 27))
    assert loss == 1.0

    for call in cur.execute.call_args_list:
        assert "adjusted_equity" in call[0][0]
        assert "daily_return_pct" not in call[0][0]


def test_weekly_loss_uses_adjusted_equity_not_raw_total_portfolio_value():
    cur = MagicMock()
    cur.fetchone.return_value = {"cur_val": 95000.0, "week_ago_val": 100000.0}
    loss = module._compute_weekly_loss(cur, date(2026, 7, 27))
    assert loss == 5.0

    sql = cur.execute.call_args[0][0]
    assert "adjusted_equity" in sql
    assert "total_portfolio_value" not in sql
