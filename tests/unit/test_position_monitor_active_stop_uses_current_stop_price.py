#!/usr/bin/env python3
"""Regression test: PositionMonitor._evaluate_position's active_stop must come from the
live current_stop_price column, not the frozen entry-time stop_loss_price.

Found live 2026-08-03: review_positions()'s SELECT (algo/monitoring/position_monitor.py)
listed `p.stop_loss_price` as its 13th column instead of `p.current_stop_price` - the
identical frozen entry-time value as the 4th column (stop_loss_price/init_stop), never the
live trailing stop that _raise_stop() (executor_exit_handler.py) actually updates. Since
`active_stop = float(current_stop) if current_stop else init_stop` always received that same
frozen value, every STOP_LOSS_HIT/trailing-stop decision compared price against the ORIGINAL
entry stop forever, silently ignoring every stop-raise ever applied - live-confirmed against a
real open position (DAC) whose real current_stop_price ($125.83, 6% below market - safe)
disagreed with its frozen stop_loss_price ($135.43, above market), producing a false
EARLY_EXIT/STOP_LOSS_HIT recommendation for a healthy position. Fixed by selecting
p.current_stop_price at that position instead.
"""

from datetime import date
from unittest.mock import patch

from algo.monitoring.position_monitor import PositionMonitor


class TestActiveStopUsesLiveCurrentStopPrice:
    def _make_monitor(self):
        return PositionMonitor(config={
            "max_hold_days": 90,
            "move_be_at_r": 1.5,
            "max_distribution_days": 5,
            "position_halt_flag_count": 3,
        })

    def _row(self, stop_loss_price, current_stop_price):
        # Row shape matches the SELECT in review_positions()/_review_with_cursor():
        # (position_id, symbol, entry_price, stop_loss_price, t1, t2, t3, entry_date,
        #  created_at, quantity, target_levels_hit, trade_ids_arr, current_stop_price, current_price)
        return (
            1, "DAC", 142.045, stop_loss_price, None, None, None,
            date(2026, 7, 20), date(2026, 7, 20), 13, 0, ["TRD-B2522D6400"],
            current_stop_price, 133.81,
        )

    def test_active_stop_uses_current_stop_price_not_frozen_stop_loss_price(self):
        """A position whose trailing stop was raised (current_stop_price != stop_loss_price)
        must be evaluated against the live current_stop_price, not the original entry stop."""
        monitor = self._make_monitor()
        # Mirrors the real DAC data this bug was caught against: frozen stop_loss_price
        # (135.43) sits ABOVE current price (133.81) - would falsely trigger a stop-hit -
        # while the real current_stop_price (125.83) sits safely below it.
        row = self._row(stop_loss_price=135.43, current_stop_price=125.8252)
        with patch.object(monitor, "_fetch_current_market", return_value=(133.81, 5.0, 130.0, 130.0)), \
             patch.object(monitor, "_check_relative_strength", return_value="neutral"), \
             patch.object(monitor, "_check_sector_health", return_value="neutral"), \
             patch.object(monitor, "_max_unrealized_pct", return_value=0.0), \
             patch.object(monitor, "_days_to_earnings", return_value=30), \
             patch.object(monitor, "_fetch_market_dist_days", return_value=0):
            rec = monitor._evaluate_position(row, date(2026, 8, 3))

        assert rec["active_stop"] == 125.8252, (
            f"active_stop must equal the live current_stop_price (125.8252), "
            f"got {rec['active_stop']} - regressed to using frozen stop_loss_price"
        )
        assert rec["action"] != "EARLY_EXIT", (
            "Must not falsely trigger EARLY_EXIT/STOP_LOSS_HIT when current price is above "
            "the real (raised) current_stop_price, even though it's below the stale stop_loss_price"
        )

    def test_stop_hit_still_fires_against_the_real_current_stop_price(self):
        """Sanity check the other direction: a genuine breach of the live current_stop_price
        must still trigger EARLY_EXIT, proving the fix didn't just disable the check."""
        monitor = self._make_monitor()
        row = self._row(stop_loss_price=100.0, current_stop_price=130.0)
        with patch.object(monitor, "_fetch_current_market", return_value=(125.0, 5.0, 128.0, 128.0)):
            rec = monitor._evaluate_position(row, date(2026, 8, 3))

        assert rec["active_stop"] == 130.0
        assert rec["action"] == "EARLY_EXIT"
        assert "STOP_LOSS_HIT" in rec["flags"]
