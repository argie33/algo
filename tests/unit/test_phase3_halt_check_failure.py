#!/usr/bin/env python3
"""Regression test for the 2026-07-26 fix: Phase 3 (position monitor) used to log a halt-check
failure as recoverable=True/"warning" and then fall through to check_stale_orders()/
review_positions() as if halt checking had succeeded - silently defeating the "GOVERNANCE:
Fail-fast if halt checks failed" raise a few lines above it. A stock that's actually halted
but whose halt check failed to confirm that (API error, missing halt data, etc.) would flow
straight into position review and downstream entry/exit phases with its halt status simply
unknown. Fixed to actually halt the phase (return halted=True) instead of continuing.
"""

from datetime import date
from unittest.mock import MagicMock, patch

from algo.orchestrator.phase3_position_monitor import run as phase3_run


def _live_config():
    return {"execution_mode": "auto", "is_paper_trading": False}


class TestPhase3HaltCheckFailureActuallyHalts:
    def test_get_open_positions_failure_halts_phase(self):
        """get_open_positions() raising must halt Phase 3, not just log and continue."""
        with (
            patch("algo.monitoring.PositionMonitor") as MockMonitor,
            patch("algo.infrastructure.MarketEventHandler") as MockMEH,
        ):
            monitor = MockMonitor.return_value
            monitor.get_open_positions.side_effect = RuntimeError("DB unavailable")
            MockMEH.return_value = MagicMock()

            result = phase3_run(
                config=_live_config(),
                run_date=date(2026, 7, 15),
                dry_run=False,
                alerts=MagicMock(),
                verbose=False,
                log_phase_result_fn=MagicMock(),
            )

        assert result.halted is True, "Phase 3 must halt when open positions can't be fetched for halt checking"
        assert result.status != "ok"
        # Must NOT have proceeded to review positions and report false success
        monitor.review_positions.assert_not_called()

    def test_halt_check_error_for_a_position_halts_phase(self):
        """A single symbol's halt check erroring (not just total fetch failure) must also halt,
        matching the explicit 'GOVERNANCE: Fail-fast if halt checks failed' raise in the code."""
        with (
            patch("algo.monitoring.PositionMonitor") as MockMonitor,
            patch("algo.infrastructure.MarketEventHandler") as MockMEH,
        ):
            monitor = MockMonitor.return_value
            monitor.get_open_positions.return_value = [{"symbol": "AAPL"}]
            meh = MagicMock()
            meh.check_single_stock_halt.return_value = {"error": True, "reason": "API timeout"}
            MockMEH.return_value = meh

            result = phase3_run(
                config=_live_config(),
                run_date=date(2026, 7, 15),
                dry_run=False,
                alerts=MagicMock(),
                verbose=False,
                log_phase_result_fn=MagicMock(),
            )

        assert result.halted is True, "Phase 3 must halt when a position's halt status can't be verified"
        monitor.review_positions.assert_not_called()

    def test_successful_halt_checks_do_not_halt(self):
        """Sanity check: when halt checking succeeds cleanly, the phase must proceed normally
        (guards against a fix that halts unconditionally instead of only on real failure)."""
        with (
            patch("algo.monitoring.PositionMonitor") as MockMonitor,
            patch("algo.infrastructure.MarketEventHandler") as MockMEH,
        ):
            monitor = MockMonitor.return_value
            monitor.get_open_positions.return_value = [{"symbol": "AAPL"}]
            monitor.check_stale_orders.return_value = {"status": "OK"}
            monitor.review_positions.return_value = []
            meh = MagicMock()
            meh.check_single_stock_halt.return_value = {"halted": False}
            MockMEH.return_value = meh

            result = phase3_run(
                config=_live_config(),
                run_date=date(2026, 7, 15),
                dry_run=False,
                alerts=MagicMock(),
                verbose=False,
                log_phase_result_fn=MagicMock(),
            )

        assert result.halted is False
        assert result.status == "ok"
