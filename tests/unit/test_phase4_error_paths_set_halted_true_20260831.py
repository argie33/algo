#!/usr/bin/env python3
"""Regression test for the 2026-08-31 (/goal pre-real-money audit) fix: Phase 4's ValueError,
generic-Exception, and DatabaseError/OperationalError handlers all returned
`PhaseResult(..., halted=False, ...)` despite their own comments/reasoning treating the failure
as critical. As of this fix, `PhaseResult.ok` (computed from `status`, not `halted`) is what
actually gates phase_executor.py's dependency chain today, so this had no live behavioral effect
- but left the flag meaning the opposite of its own stated intent for any future code that keys
off `.halted` specifically for this phase. Fixed to set halted=True on all three, matching every
other phase's convention for its own critical/fail-fast error paths.

The DB-error branch was initially left untouched pending a closer look at its `recoverable=True`
marking (see phase2_phase4_phase5_orchestrator_wrappers_reviewed_20260831 in memory for the full
history) - a repo-wide grep confirmed `PhaseError.recoverable` is diagnostic-only (feeds
`to_dict()` for logging, gates nothing) and is unrelated to `PhaseResult.halted`, so it was fixed
too: a reconciliation DB error means broker-vs-DB position state can't be verified, and entering
new trades without that verification is exactly the "cannot proceed without X" case this codebase
treats as critical everywhere else.

The broker-unavailable/401 branch's weekday/weekend distinction is covered separately in
tests/unit/test_phase4_broker_unavailable_weekday_weekend_20260831.py.
"""

from datetime import date
from unittest.mock import MagicMock, patch

import psycopg2

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

    def test_database_error_sets_halted_true(self):
        result = _run_with_recon_side_effect(psycopg2.OperationalError("connection to server lost"))

        assert result.status == "error"
        assert result.halted is True, (
            "A DB error means broker-vs-DB position state can't be verified - entering new "
            "trades without that verification is a real risk. halted must be True; "
            "PhaseError.recoverable=True is unrelated diagnostic metadata, not a reason to "
            "leave PhaseResult.halted=False (confirmed via repo-wide grep: recoverable feeds "
            "only PhaseError.to_dict() logging, gates no control flow)"
        )


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
