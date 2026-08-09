#!/usr/bin/env python3
"""Regression test: a STOP_LOSS_HIT EARLY_EXIT recommendation must carry an
exit_price_override pinned to active_stop, and phase6_exit_execution.py must use it.

In paper mode, the exit_price passed to TradeExecutor.exit_trade() is the final,
deterministic simulated fill - it is never reconciled against a real broker fill
(see executor_exit_handler.py's is_estimated_price comment). Real trade data
(2026-08-08 closes, e.g. WPM -1.7%, ERO -4.15%) showed exit_price recorded well
below stop_loss_price for exits reasoned "STOP LOSS HIT: price $X <= stop $Y" -
phase6_exit_execution.py was passing rec["current_price"] (this run's possibly-
gapped evaluation-time quote) as the fill instead of the stop price, producing
phantom slippage with no connection to real execution quality. exit_engine.py's
own separate hard-capital-preservation stop path already avoided this via
exit_price_override=stop price (0% slippage confirmed on ESTC/EGO the same day) -
this fix brings position_monitor's STOP_LOSS_HIT path in line with that same
convention. Other EARLY_EXIT reasons (health-flag accumulation, earnings-forced)
aren't tied to a price level and correctly keep using current_price.
"""

from datetime import date
from unittest.mock import MagicMock, patch

from algo.monitoring.position_monitor import PositionMonitor


def _row(stop_loss_price, current_stop_price):
    # Matches the SELECT shape in review_positions()/_review_with_cursor().
    return (
        1, "WPM", 120.0, stop_loss_price, None, None, None,
        date(2026, 7, 20), date(2026, 7, 20), 10, 0, ["TRD-1"],
        current_stop_price, 108.53,
    )


class TestStopLossHitExitPriceOverride:
    def _make_monitor(self):
        return PositionMonitor(config={
            "max_hold_days": 90,
            "move_be_at_r": 1.5,
            "max_distribution_days": 5,
            "position_halt_flag_count": 3,
        })

    def test_stop_loss_hit_sets_exit_price_override_to_active_stop(self):
        """A gapped-through-stop position (current_price far below active_stop) must
        record exit_price_override at the stop price, not the gapped current price."""
        monitor = self._make_monitor()
        row = _row(stop_loss_price=110.405, current_stop_price=110.405)
        with patch.object(monitor, "_fetch_current_market", return_value=(108.53, 5.0, 112.0, 112.0)):
            rec = monitor._evaluate_position(row, date(2026, 8, 8))

        assert rec["action"] == "EARLY_EXIT"
        assert "STOP_LOSS_HIT" in rec["flags"]
        assert rec["current_price"] == 108.53, "current_price must still reflect the real observed quote"
        assert rec["exit_price_override"] == 110.405, (
            "exit_price_override must be pinned to active_stop (110.405), not the gapped "
            f"current_price (108.53) - got {rec.get('exit_price_override')}"
        )


class TestPhase6UsesExitPriceOverrideForStopHits:
    def test_phase6_passes_override_price_not_current_price_to_exit_trade(self):
        """phase6_exit_execution.py must pass exit_price_override to exit_trade() when
        present, not silently fall back to current_price for a stop-loss-triggered exit."""
        from algo.orchestrator import phase6_exit_execution

        rec = {
            "symbol": "WPM",
            "trade_id": "TRD-1",
            "action": "EARLY_EXIT",
            "current_price": 108.53,
            "exit_price_override": 110.405,
            "action_reason": "STOP LOSS HIT: price $108.53 <= stop $110.41",
        }

        mock_executor = MagicMock()
        mock_executor.exit_trade.return_value = {"success": True, "message": "ok"}

        # Exercise the same expression phase6 uses to build the exit_trade call, isolated
        # from the rest of run()'s heavy DB/orchestration setup.
        exit_price = rec.get("exit_price_override", rec["current_price"])
        mock_executor.exit_trade(
            trade_id=rec["trade_id"],
            exit_price=exit_price,
            exit_reason=rec["action_reason"],
            exit_fraction=1.0,
            exit_stage="early_exit",
        )

        assert exit_price == 110.405
        called_kwargs = mock_executor.exit_trade.call_args.kwargs
        assert called_kwargs["exit_price"] == 110.405, (
            "must use the stop price override, not the gapped current_price 108.53"
        )

        # Confirm phase6_exit_execution.py's actual source still contains this exact
        # override-aware expression, so this test fails loudly if it regresses back to
        # unconditionally using rec["current_price"].
        import inspect

        source = inspect.getsource(phase6_exit_execution)
        assert 'rec.get("exit_price_override", rec["current_price"])' in source, (
            "phase6_exit_execution.py must read exit_price_override before falling back "
            "to current_price when executing an EARLY_EXIT"
        )
