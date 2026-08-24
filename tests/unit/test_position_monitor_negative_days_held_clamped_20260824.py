"""Regression test (2026-08-24, real-money-readiness goal session).

algo/trading/exit_engine.py's days_held computation clamps a negative result (trade_date
after the evaluation date - a data-corruption signal, e.g. a bad DB write) to 0 and logs a
WARNING flagging it. algo/monitoring/position_monitor.py's _evaluate_position() computes the
identical quantity (added in the same 2026-08-24 trading-day-aware fix, see
test_days_held_trading_day_aware_20260824.py) but silently used the raw negative value with
no warning - harmless for today's `days_held >= N` comparisons (a negative value never trips
them), but it hid a real corruption signal and diverged from the sibling call site's own
stated behavior (that test's docstring already claims both callers clamp+warn). Fixed by
matching exit_engine.py's clamp-and-warn pattern here too.
"""

import logging
from datetime import date
from unittest.mock import patch

from algo.monitoring.position_monitor import PositionMonitor


def _row(trade_date):
    # Matches the SELECT shape in review_positions()/_review_with_cursor() - see
    # test_position_monitor_active_stop_reason_distinguishes_profit_lock.py's _row(). Uses
    # that file's "genuine stop-loss hit" numbers (entry 120.0/stop 110.405/price 108.53) so
    # _evaluate_position takes the early stop-hit return path, which is reached right after
    # days_held is computed - avoiding the need to also mock _check_relative_strength's DB
    # cursor for a code path this test isn't about.
    return (
        1,
        "MRK",
        120.0,
        110.405,
        None,
        None,
        None,
        trade_date,
        None,
        25,
        3,
        ["TRD-1"],
        110.405,
        None,
    )


def _make_monitor():
    return PositionMonitor(
        config={
            "max_hold_days": 90,
            "move_be_at_r": 1.5,
            "max_distribution_days": 5,
            "position_halt_flag_count": 3,
        }
    )


class TestNegativeDaysHeldClampedWithWarning:
    def test_future_trade_date_clamps_days_held_to_zero_and_warns(self, caplog):
        """trade_date after the evaluation date (data corruption) must clamp days_held to 0,
        not silently propagate a negative value, and must log a warning about it."""
        monitor = _make_monitor()
        row = _row(trade_date=date(2026, 8, 24))
        eval_date = date(2026, 8, 19)  # before trade_date -> negative trading_days_elapsed

        with (
            patch.object(monitor, "_fetch_current_market", return_value=(108.53, 5.0, 112.0, 112.0)),
            caplog.at_level(logging.WARNING, logger="algo.monitoring.position_monitor"),
        ):
            rec = monitor._evaluate_position(row, eval_date)

        assert rec["days_held"] == 0
        assert any("days_held is negative" in msg for msg in caplog.messages), (
            "a future trade_date is a real data-corruption signal and must be logged, "
            "matching exit_engine.py's identical clamp-and-warn behavior"
        )

    def test_normal_trade_date_does_not_warn(self, caplog):
        """Sanity check: the fix must not introduce a spurious warning on the normal path."""
        monitor = _make_monitor()
        row = _row(trade_date=date(2026, 8, 18))
        eval_date = date(2026, 8, 19)

        with (
            patch.object(monitor, "_fetch_current_market", return_value=(108.53, 5.0, 112.0, 112.0)),
            caplog.at_level(logging.WARNING, logger="algo.monitoring.position_monitor"),
        ):
            rec = monitor._evaluate_position(row, eval_date)

        assert rec["days_held"] == 1
        assert not any("days_held is negative" in msg for msg in caplog.messages)
