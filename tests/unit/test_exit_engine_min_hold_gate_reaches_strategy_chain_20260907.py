#!/usr/bin/env python3
"""Regression test for a bug where check_and_execute_exits' own min_hold_days branch
(exit_engine.py, in the `else:` arm right after the hard init_stop check) gated the ENTIRE
call to `_evaluate_position` behind `days_held < min_hold_days`, `continue`-ing past it
whenever a position was still inside the min-hold window.

That silently made 10 of the 11 documented exit strategies (Minervini break, RS-line break,
T1/T2/T3 targets, chandelier trail, TD Sequential, first-red-day, climax exhaustion,
distribution-day de-risking, and even the trailing/raised `active_stop` check inside
`_evaluate_position`) unreachable during the min-hold window - even though `_evaluate_position`
itself (see its "CRITICAL FIX SESSION 41" comment) was specifically rewritten to allow exactly
these signals through during that window, gating only time-based exits via check_time_exit.
The outer gate meant that rewrite was dead code: `_evaluate_position` was never invoked at all
for a same-day (days_held=0) position unless the raw init_stop was hit first.

Concrete production impact: min_hold_days=1 in prod, so a position entered today that gaps
up hard and blows through T1/T2/T3, or hits a legitimate Minervini/distribution-day trigger,
got none of that evaluated - it rode the original static stop only, with no breakeven raise,
partial profit-take, or de-risking, until the next trading day. Also silently reintroduces the
exact "positions stuck, can't exit, blocks new entries" deadlock the SESSION 41 fix was written
to close.

Fix: remove the outer gate entirely (except for the untouched, unconditional init_stop check
above it) so `_evaluate_position` is always reached; min_hold_days enforcement for time-based
exits remains inside check_time_exit, as SESSION 41 already documented.
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
        "exit_on_distribution_day": True,
        "max_distribution_days": 4,
        "move_be_at_r": 1.0,
        "chandelier_atr_mult": 3.0,
        "use_chandelier_trail": False,
        "exit_on_td_sequential": False,
        "exit_on_rs_line_break_50dma": False,
        "require_target_pullback": True,
        "use_scale_out_targets": True,
        "execution_mode": "paper",
        "alpaca_paper_trading": True,
    }


def test_same_day_entry_still_reaches_evaluate_position_not_just_init_stop():
    """A position entered TODAY (days_held=0, below min_hold_days=1) whose current price has
    NOT hit the raw init_stop must still have `_evaluate_position` invoked - the outer
    min_hold_days branch must not `continue` past it. Before the fix, `_evaluate_position` was
    never called in this scenario at all."""
    trade_row = (
        "TRD-1",  # trade_id
        "GAPUP",  # symbol
        100.0,  # entry_price
        90.0,  # stop_loss_price (init_stop) - NOT hit by cur_price below
        115.0,
        130.0,
        140.0,  # t1/t2/t3 price
        date(2026, 9, 7),  # trade_date == current_date -> days_held == 0
        "POS-1",  # position_id
        10,  # quantity
        0,  # target_levels_hit
        90.0,  # current_stop_price (active_stop) - also not hit
        None,
        None,
        None,  # t1/t2/t3 hit times
        None,  # last_partial_exit_date
        None,  # partial_exits_log
    )

    mock_cur = MagicMock()
    mock_cur.fetchall.return_value = [trade_row]
    mock_cur.fetchone.return_value = ("open", 10, 90.0)

    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_cur
    mock_ctx.__exit__.return_value = False

    with patch("algo.trading.exit_engine.TradeExecutor"):
        engine = ExitEngine(_mock_config())

        with (
            patch("algo.trading.exit_engine.DatabaseContext", return_value=mock_ctx),
            patch.object(engine, "_fetch_market_dist_days", return_value=set()),
            # Price well above both init_stop (90) and active_stop (90) - the hard-stop
            # branches above the min_hold_days gate must NOT be what triggers evaluation.
            patch.object(engine, "_fetch_recent_prices", return_value=(150.0, 149.0)),
            patch.object(engine, "_evaluate_position", return_value=None) as mock_evaluate,
        ):
            engine.check_and_execute_exits(date(2026, 9, 7))

    assert mock_evaluate.called, (
        "_evaluate_position was never invoked for a same-day (days_held=0) position whose "
        "price is above the hard stop - the min_hold_days branch is swallowing it before the "
        "ExitStrategyChain (targets, distribution, trailing stop, etc.) ever runs."
    )
    args, kwargs = mock_evaluate.call_args
    days_held_arg = kwargs.get("days_held", args[12] if len(args) > 12 else None)
    assert days_held_arg == 0, (
        f"expected _evaluate_position to be called with days_held=0 for a same-day entry, got {days_held_arg}"
    )
