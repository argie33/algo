#!/usr/bin/env python3
"""Regression test for phase4_reconciliation.run() reporting status "success"/"ok" even when
result["final_verification_failed"] is True.

The code has a comment directly above this block stating the failed verification "must not
be silently absorbed into an unqualified success" - but the status passed to
log_phase_result_fn and the returned PhaseResult.status were both hardcoded regardless of
final_verification_failed, contradicting the comment. "degraded" is safe here: PhaseResult.ok
treats "degraded" as success for downstream dependency checks (Phase 5+ still proceed), it just
stops being indistinguishable from a genuinely clean run in phase status / dashboard views.
"""

from unittest.mock import MagicMock, patch

import pytest

from algo.orchestrator.phase4_reconciliation import run


@pytest.fixture
def mock_config():
    cfg = MagicMock()
    cfg.get.return_value = "paper"
    return cfg


def _run_with_result(recon_result, mock_config):
    mock_recon = MagicMock()
    mock_recon.run_daily_reconciliation.return_value = recon_result
    mock_recon.check_partial_fills.return_value = {"mismatches": 0, "no_broker": True}

    mock_cur = MagicMock()
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = mock_cur
    mock_ctx.__exit__.return_value = False

    logged = []

    def fake_log(phase_num, name, status, summary):
        logged.append((phase_num, name, status, summary))

    with (
        patch("algo.infrastructure.reconciliation.DailyReconciliation", return_value=mock_recon),
        patch("utils.db.DatabaseContext", return_value=mock_ctx),
    ):
        result = run(
            config=mock_config,
            run_date=__import__("datetime").date(2026, 7, 22),
            dry_run=False,
            alerts=MagicMock(),
            verbose=False,
            log_phase_result_fn=fake_log,
        )
    return result, logged


def test_final_verification_failed_reports_degraded_not_success(mock_config):
    recon_result = {
        "success": True,
        "reason": "reconciled",
        "positions": 5,
        "final_verification_failed": True,
        "final_verification_detail": "portfolio snapshot row count mismatch after commit",
    }

    result, logged = _run_with_result(recon_result, mock_config)

    assert result.status == "degraded", (
        "a failed final-verification must not be reported as clean 'ok' - "
        f"got status={result.status!r}"
    )
    assert result.ok, "degraded must still count as ok for downstream Phase 5+ dependency checks"
    assert logged, "log_phase_result_fn must have been called"
    assert logged[-1][2] == "degraded"


def test_clean_reconciliation_still_reports_success(mock_config):
    recon_result = {
        "success": True,
        "reason": "reconciled",
        "positions": 5,
    }

    result, logged = _run_with_result(recon_result, mock_config)

    assert result.status == "ok"
    assert logged[-1][2] == "success"


def test_reconciliation_failure_logs_error_not_alert(mock_config):
    """Regression: log_phase_result_fn used to be called with status "alert" on reconciliation
    failure - a status string dashboard/panels/health.py's phase-execution panel doesn't
    recognize (its ERROR_STATES tuple is ("error", "failed")). "alert" fell into that panel's
    default branch and rendered as dim "NOT RUN", identical to a phase that simply hasn't
    executed yet - hiding a real broker/reconciliation failure from anyone watching the
    dashboard. Must use "error" to match this function's own PhaseResult.status for the same
    event and the vocabulary the dashboard actually classifies."""
    recon_result = {
        "success": False,
        "reason": "Alpaca API returned 401 unauthorized",
    }

    result, logged = _run_with_result(recon_result, mock_config)

    assert result.status == "error"
    assert logged, "log_phase_result_fn must have been called"
    logged_status = logged[-1][2]
    assert logged_status == "error", (
        f"expected log_phase_result_fn status 'error', got {logged_status!r} - "
        "if this is 'alert' again, the dashboard will misrender this failure as NOT RUN"
    )

    from dashboard.panels.health import ERROR_STATES, HALTED_STATES, SUCCESS_STATES

    assert logged_status not in SUCCESS_STATES
    assert logged_status not in HALTED_STATES
    assert logged_status in ERROR_STATES, (
        "the status phase4 logs on failure must be one dashboard/panels/health.py's "
        "phase-execution panel actually classifies as an error, not silently falls "
        "through to the 'NOT RUN' default"
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
