#!/usr/bin/env python3
"""Regression test for the 2026-08-31 (/goal pre-real-money audit) fix: Phase 4's ValueError
and generic-Exception handlers both returned `PhaseResult(..., halted=False, ...)` despite their
own comments explicitly saying "fail-fast" / "All reconciliation errors are critical". As of this
fix, `PhaseResult.ok` (computed from `status`, not `halted`) is what actually gates
phase_executor.py's dependency chain today, so this had no live behavioral effect - but left the
flag meaning the opposite of its own stated intent for any future code that keys off `.halted`
specifically for this phase. Fixed to set halted=True on both paths, matching every other phase's
convention for its own critical/fail-fast error paths.

The DB-error branch (psycopg2.DatabaseError/OperationalError, explicitly marked
`recoverable=True`) and the broker-unavailable/401 branch (whose own comment describes an
unimplemented weekday/weekend distinction) were deliberately NOT touched - see
phase2_phase4_phase5_orchestrator_wrappers_reviewed_20260831 in memory for why those two remain
open, unresolved design questions rather than guessed-at fixes.
"""

from datetime import date
from unittest.mock import MagicMock, patch

from algo.orchestrator.phase4_reconciliation import run


def _run_with_recon_side_effect(recon_side_effect):
    mock_config = MagicMock()
    mock_config.get.return_value = "auto"

    mock_recon = MagicMock()
    mock_recon.run_daily_reconciliation.side_effect = recon_side_effect

    mock_cur = MagicMock()
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_cur
    mock_ctx.__exit__.return_value = False

    with (
        patch("algo.infrastructure.reconciliation.DailyReconciliation", return_value=mock_recon),
        patch("utils.db.DatabaseContext", return_value=mock_ctx),
    ):
        return run(
            config=mock_config,
            run_date=date(2026, 8, 31),
            dry_run=False,
            alerts=MagicMock(),
            verbose=False,
            log_phase_result_fn=MagicMock(),
        )


class TestPhase4ErrorPathsSetHaltedTrue:
    def test_value_error_sets_halted_true(self):
        result = _run_with_recon_side_effect(ValueError("Alpaca 401 Unauthorized"))

        assert result.status == "error"
        assert result.halted is True, (
            "ValueError branch's own comment says 'fail-fast to prevent trading on stale "
            "position data' - halted must be True, not the opposite of that stated intent"
        )

    def test_generic_exception_sets_halted_true(self):
        result = _run_with_recon_side_effect(RuntimeError("unexpected reconciliation failure"))

        assert result.status == "error"
        assert result.halted is True, (
            "Generic-exception branch's own comment says 'All reconciliation errors are "
            "critical - fail-fast' - halted must be True, not the opposite of that stated intent"
        )


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
