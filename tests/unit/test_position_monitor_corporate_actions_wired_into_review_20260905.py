"""Regression test: PositionMonitor.review_positions() must actually call
check_corporate_actions() (stock-split detection/rescale) every cycle, before evaluating
individual positions.

BUG FOUND 2026-09-05 (real-money-readiness audit, stops/exits review): check_corporate_actions()
was a fully-implemented method with ZERO real callers anywhere in the orchestrator, phases,
lambda, or scheduled scripts - only its own unit tests (test_position_split_price_rescale.py)
ever invoked it, directly, bypassing review_positions() entirely. A real stock split on an
open position therefore had no mechanism to ever rescale its stop price or quantity - it
would sit at the wrong price scale (e.g. ~2x too high/low after a 2:1 split) indefinitely,
a genuinely unprotected/mis-protected position with real money at risk. Wired into
review_positions() right after the margin/sector-concentration checks and before the FOR
UPDATE position query, so any split is rescaled before _evaluate_position reads position
data for the cycle.
"""

from datetime import date
from unittest.mock import MagicMock, patch

from algo.monitoring.position_monitor import PositionMonitor


class TestCorporateActionsWiredIntoReviewPositions:
    def _make_monitor(self):
        return PositionMonitor(config={"max_hold_days": 90, "move_be_at_r": 1.5})

    def test_review_positions_calls_check_corporate_actions(self):
        monitor = self._make_monitor()
        cursor = MagicMock()
        # Portfolio snapshot query, then margin COUNT/SUM query - both read directly off the
        # shared cursor before check_sector_concentration/check_corporate_actions run.
        cursor.fetchone.side_effect = [(100000.0,), (0, None)]
        # FOR UPDATE open-positions query - empty, so the per-position loop is a no-op and
        # this test only needs to prove the corporate-actions call itself happened.
        cursor.fetchall.return_value = []

        with (
            patch.object(monitor, "check_sector_concentration", return_value={"status": "OK"}) as mock_conc,
            patch.object(monitor, "check_corporate_actions", return_value=[]) as mock_corp,
        ):
            monitor.review_positions(current_date=date(2026, 9, 5), cur=cursor)

        mock_corp.assert_called_once()
        mock_conc.assert_called_once()

    def test_corporate_action_db_error_fails_closed(self):
        """A database error during corporate-action detection must halt position review
        (PositionValidationError), matching the margin/concentration checks' own fail-closed
        pattern - proceeding with potentially stale quantities/stops after a broker-vs-DB
        verification failure is exactly the "blind risk-taking" this codebase's own
        conventions exist to prevent."""
        import psycopg2

        from algo.monitoring.position_monitor import PositionValidationError

        monitor = self._make_monitor()
        cursor = MagicMock()
        cursor.fetchone.side_effect = [(100000.0,), (0, None)]

        with (
            patch.object(monitor, "check_sector_concentration", return_value={"status": "OK"}),
            patch.object(
                monitor,
                "check_corporate_actions",
                side_effect=psycopg2.OperationalError("connection lost"),
            ),
        ):
            try:
                monitor.review_positions(current_date=date(2026, 9, 5), cur=cursor)
                raised = False
            except PositionValidationError:
                raised = True

        assert raised, "a DB error in corporate-action detection must raise PositionValidationError, not be swallowed"
