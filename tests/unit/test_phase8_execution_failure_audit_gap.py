"""Regression test: Phase 8 broker-execution failures must leave a queryable audit trail.

algo/orchestrator/phase8_entry_execution.py's _log_signal_rejection() persists skipped/
rejected signals to algo_signal_rejections, but a run this morning
(LOCAL-MORNING-20260727-103249-635466) reported "1 trades executed, 2 failed" via
logger.error() only - no row for either failure ever reached algo_signal_rejections,
because the audit call for the execution_failed/execution_error/processing_error stages
didn't exist yet at that point in the day (added later the same day, commit 4df7d36ed).
Without it, a real broker-execution failure (rejected order, API error) was undiagnosable
after the process exited - the only record was a log line, not a queryable row. This test
locks in that the fix actually persists the failure, so the gap can't silently regress.
"""

from datetime import date
from unittest.mock import MagicMock, patch

from algo.orchestrator.phase8_entry_execution import _log_signal_rejection


def test_execution_failed_is_persisted_to_signal_rejections_audit_table():
    mock_cur = MagicMock()

    with patch("algo.orchestrator.phase8_entry_execution.DatabaseContext") as mock_ctx:
        mock_ctx.return_value.__enter__.return_value = mock_cur

        _log_signal_rejection(
            "KEX", "execution_failed", "Order rejected (status=rejected)", date(2026, 7, 27), 149.15, 1.5
        )

    mock_cur.execute.assert_called_once()
    sql, params = mock_cur.execute.call_args[0]
    assert "algo_signal_rejections" in sql
    assert params == (date(2026, 7, 27), "KEX", "execution_failed", "Order rejected (status=rejected)", 149.15, 1.5)


def test_audit_failure_itself_raises_rather_than_silently_dropping():
    """If the audit insert itself fails, the caller must find out (raise), not swallow it -
    a silently-failing audit trail is worse than no audit trail (false confidence)."""
    with patch("algo.orchestrator.phase8_entry_execution.DatabaseContext") as mock_ctx:
        mock_ctx.return_value.__enter__.side_effect = RuntimeError("connection lost")

        try:
            _log_signal_rejection("KEX", "execution_failed", "boom", date(2026, 7, 27))
            raised = False
        except RuntimeError:
            raised = True

    assert raised
