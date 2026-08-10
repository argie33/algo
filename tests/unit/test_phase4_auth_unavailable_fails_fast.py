"""Regression test for Phase 4's broker-auth-unavailable fail-fast path.

phase4_reconciliation.py's own comment marks this as safety-critical: "FAIL-FAST: Cannot
validate partial fills without broker auth ... Continuing with unvalidated partial fills
risks position state divergence and incorrect risk calculations." This is distinct from the
no_broker (paper mode) case, which is expected and must NOT halt - auth_unavailable means a
real broker credential/auth failure in a mode that expects a working broker connection, and
had zero dynamic test coverage before this (existing test_phase4_final_verification_status.py
only exercises the no_broker=True paper-mode fixture, never the auth_unavailable branch).

Follows the same mocking pattern as that existing test file (patch DailyReconciliation +
DatabaseContext) rather than a live broker/DB test, since this needs to simulate a genuine
Alpaca 401 without ever making a real network call or touching shared dev state.
"""

from datetime import date
from unittest.mock import MagicMock, patch

from algo.orchestrator.phase4_reconciliation import run


def _run_with_partial_fill_result(partial_fill_result):
    mock_config = MagicMock()
    mock_config.get.return_value = "auto"

    mock_recon = MagicMock()
    mock_recon.run_daily_reconciliation.return_value = {
        "success": True,
        "reason": "ok",
        "positions": 13,
    }
    mock_recon.check_partial_fills.return_value = partial_fill_result

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
            run_date=date(2026, 8, 10),
            dry_run=False,
            alerts=MagicMock(),
            verbose=False,
            log_phase_result_fn=fake_log,
        )
    return result, logged


class TestPhase4AuthUnavailableFailsFast:
    def test_auth_unavailable_halts_phase_4(self):
        """The core safety property: a real broker auth failure must produce an error
        PhaseResult, not silently proceed with unvalidated partial fills."""
        result, _logged = _run_with_partial_fill_result({"mismatches": 0, "auth_unavailable": True})

        assert result.status == "error"
        assert "auth" in result.error.lower()

    def test_no_broker_paper_mode_does_not_halt(self):
        """Companion sanity check: the no_broker (paper mode) case must NOT be conflated
        with auth_unavailable - paper mode legitimately never has a broker to check."""
        result, _logged = _run_with_partial_fill_result({"mismatches": 0, "no_broker": True})

        assert result.status != "error"

    def test_real_partial_fill_mismatches_are_detected_not_swallowed(self):
        """A genuine partial-fill mismatch (broker quantity differs from DB) must be
        recorded, not silently treated the same as 0 mismatches."""
        result, _logged = _run_with_partial_fill_result({"mismatches": 3, "no_broker": False})

        assert result.status != "error"
        assert result.data.get("partial_fill_corrections", {}).get("mismatches") == 3
