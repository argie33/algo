"""Regression tests for DailyReconciliation._track_and_maybe_halt_on_sustained_drift -
the auto-halt-on-sustained-broker/DB-equity-drift escalation added 2026-09-07 real-money-
readiness audit, mirroring unified_risk_monitor.py's consecutive-breach ladder but for a
halt (not the riskier auto-flatten), reusing algo_risk_monitor_state's generic schema.
"""

from decimal import Decimal
from unittest.mock import MagicMock, patch

from algo.infrastructure.reconciliation import DailyReconciliation


def _instance() -> DailyReconciliation:
    """Skip __init__ (needs full config/broker setup unrelated to this method)."""
    return DailyReconciliation.__new__(DailyReconciliation)


def _mock_cursor(prior_count: int | None):
    cur = MagicMock()
    cur.fetchone.return_value = (prior_count,) if prior_count is not None else None
    return cur


class TestSustainedDriftAutoHalt:
    def test_first_critical_drift_tracks_but_does_not_halt(self):
        recon = _instance()
        cur = _mock_cursor(prior_count=0)
        with patch("algo.orchestration.halt_flag_manager.HaltFlagManager") as mock_hfm:
            recon._track_and_maybe_halt_on_sustained_drift(
                cur, True, Decimal("7.0"), Decimal("107000"), Decimal("100000")
            )
        mock_hfm.assert_not_called()
        insert_call = next(c for c in cur.execute.call_args_list if "INSERT INTO algo_risk_monitor_state" in c.args[0])
        assert insert_call.args[1][1] == 1  # new_count = prior(0) + 1

    def test_second_consecutive_critical_drift_shadow_mode_does_not_halt(self):
        """Default (no self.config / shadow mode on): observes and alerts but does not halt."""
        recon = _instance()
        cur = _mock_cursor(prior_count=1)
        with (
            patch("algo.orchestration.halt_flag_manager.HaltFlagManager") as mock_hfm_cls,
            patch("algo.reporting.AlertManager") as mock_alert_cls,
        ):
            recon._track_and_maybe_halt_on_sustained_drift(
                cur, True, Decimal("7.0"), Decimal("107000"), Decimal("100000")
            )
        mock_hfm_cls.assert_not_called()
        mock_alert_cls.return_value.send_position_alert.assert_called_once()

    def test_second_consecutive_critical_drift_halts_when_shadow_mode_disabled(self):
        recon = _instance()
        recon.config = {"reconciliation_drift_halt_shadow_mode": False}
        cur = _mock_cursor(prior_count=1)
        mock_manager = MagicMock()
        with patch("algo.orchestration.halt_flag_manager.HaltFlagManager", return_value=mock_manager) as mock_hfm_cls:
            recon._track_and_maybe_halt_on_sustained_drift(
                cur, True, Decimal("7.0"), Decimal("107000"), Decimal("100000")
            )
        mock_hfm_cls.assert_called_once()
        mock_manager.set_halt_flag.assert_called_once()
        call_kwargs = mock_manager.set_halt_flag.call_args
        assert call_kwargs.kwargs["triggered_by"] == "reconciliation_equity_drift"

    def test_non_critical_run_resets_streak_to_zero(self):
        recon = _instance()
        cur = _mock_cursor(prior_count=1)
        with patch("algo.orchestration.halt_flag_manager.HaltFlagManager") as mock_hfm_cls:
            recon._track_and_maybe_halt_on_sustained_drift(
                cur, False, Decimal("0.5"), Decimal("100500"), Decimal("100000")
            )
        mock_hfm_cls.assert_not_called()
        insert_call = next(c for c in cur.execute.call_args_list if "INSERT INTO algo_risk_monitor_state" in c.args[0])
        assert insert_call.args[1][1] == 0  # streak reset

    def test_no_prior_row_treated_as_zero_streak(self):
        recon = _instance()
        cur = _mock_cursor(prior_count=None)  # fetchone() returns None (no row yet)
        with patch("algo.orchestration.halt_flag_manager.HaltFlagManager") as mock_hfm_cls:
            recon._track_and_maybe_halt_on_sustained_drift(
                cur, True, Decimal("6.0"), Decimal("106000"), Decimal("100000")
            )
        mock_hfm_cls.assert_not_called()  # only streak 1, not yet >= 2
        insert_call = next(c for c in cur.execute.call_args_list if "INSERT INTO algo_risk_monitor_state" in c.args[0])
        assert insert_call.args[1][1] == 1

    def test_db_error_during_tracking_is_swallowed_not_raised(self):
        import psycopg2

        recon = _instance()
        cur = MagicMock()
        cur.execute.side_effect = psycopg2.OperationalError("connection lost")
        # Must not raise - this is best-effort bookkeeping, never allowed to fail reconciliation.
        recon._track_and_maybe_halt_on_sustained_drift(cur, True, Decimal("7.0"), Decimal("107000"), Decimal("100000"))

    def test_halt_manager_failure_is_swallowed_not_raised(self):
        recon = _instance()
        recon.config = {"reconciliation_drift_halt_shadow_mode": False}
        cur = _mock_cursor(prior_count=1)
        with patch("algo.orchestration.halt_flag_manager.HaltFlagManager", side_effect=RuntimeError("boom")):
            # Must not raise even though set_halt_flag construction failed.
            recon._track_and_maybe_halt_on_sustained_drift(
                cur, True, Decimal("7.0"), Decimal("107000"), Decimal("100000")
            )
