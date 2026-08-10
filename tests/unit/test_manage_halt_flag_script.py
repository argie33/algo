"""Regression test for scripts/manage_halt_flag.py, the manual operator halt-control tool.

Built alongside halt_flag_cleared_by_unrelated_phase_fix_20260810: before this, there was no
way for a human operator to durably halt or resume trading. This script fills that gap,
tagging manually-set halts as triggered_by="manual_operator" so Phase 1's freshness check
(fixed the same session) won't silently clear them.

Live-verified separately (not just this mocked test): --set/--status/--clear against the
real local DB, and confirmed a manually-set halt survives a full orchestrator invocation
exactly like a phase9-triggered one does.
"""

from unittest.mock import MagicMock, patch

import scripts.manage_halt_flag as manage_halt_flag


def _run(argv):
    import sys

    with patch.object(sys, "argv", ["manage_halt_flag.py"] + argv):
        return manage_halt_flag.main()


class TestManageHaltFlagScript:
    def test_set_tags_halt_as_manual_operator(self):
        mock_manager = MagicMock()
        mock_manager.set_halt_flag.return_value = True
        with patch.object(manage_halt_flag, "HaltFlagManager", return_value=mock_manager):
            exit_code = _run(["--set", "stop trading now"])

        assert exit_code == 0
        # force=True: regression coverage for the 2026-08-10 sticky-trigger bug (live-reproduced) -
        # without it, a manual halt set while an automated halt is already active gets silently
        # absorbed into that automated halt's triggered_by/reason and can be auto-cleared alongside
        # it, despite this script printing "Trading is now halted until explicitly cleared".
        mock_manager.set_halt_flag.assert_called_once_with(
            "stop trading now", triggered_by="manual_operator", force=True
        )

    def test_set_failure_returns_nonzero(self):
        mock_manager = MagicMock()
        mock_manager.set_halt_flag.return_value = False
        with patch.object(manage_halt_flag, "HaltFlagManager", return_value=mock_manager):
            exit_code = _run(["--set", "stop trading now"])

        assert exit_code == 1

    def test_clear_invokes_clear_halt_flag(self):
        mock_manager = MagicMock()
        mock_manager.get_halt_triggered_by.return_value = "manual_operator"
        with patch.object(manage_halt_flag, "HaltFlagManager", return_value=mock_manager):
            exit_code = _run(["--clear", "resuming trading"])

        assert exit_code == 0
        mock_manager.clear_halt_flag.assert_called_once()

    def test_status_reports_active_halt_and_its_origin(self, capsys):
        mock_manager = MagicMock()
        mock_manager.check_halt_flag.return_value = True
        mock_manager.get_halt_triggered_by.return_value = "phase9_reconciliation_governance"
        with patch.object(manage_halt_flag, "HaltFlagManager", return_value=mock_manager):
            exit_code = _run(["--status"])

        assert exit_code == 0
        out = capsys.readouterr().out
        assert "Halted: True" in out
        assert "phase9_reconciliation_governance" in out

    def test_status_reports_not_halted(self, capsys):
        mock_manager = MagicMock()
        mock_manager.check_halt_flag.return_value = False
        with patch.object(manage_halt_flag, "HaltFlagManager", return_value=mock_manager):
            exit_code = _run(["--status"])

        assert exit_code == 0
        out = capsys.readouterr().out
        assert "Halted: False" in out
        mock_manager.get_halt_triggered_by.assert_not_called()
