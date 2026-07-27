"""Regression test: a DB error in Phase 9's _update_daily_metrics() must surface as the
intended RuntimeError, not an UnboundLocalError from its own finally block.

Unlike its three sibling functions (_validate_pnl_step, _compute_performance_metrics,
_compute_risk_metrics), _update_daily_metrics() only assigned metrics_status/metrics_summary
inside the try body's success/no-trades branches, not before the try. A
psycopg2.DatabaseError/OperationalError raised before either branch runs (e.g. during the
SELECTs or the INSERT) hit the except clause, which built the intended "[PHASE 9 CRITICAL]
Failed to persist metrics..." RuntimeError - but the finally block then referenced the still-
unassigned locals, raising UnboundLocalError from inside finally, which replaced that
RuntimeError as the exception actually propagated to the caller. Confirmed live 2026-07-27.
"""

from datetime import date
from unittest.mock import MagicMock, patch

import psycopg2
import pytest

from algo.orchestrator.phase9_reconciliation import _update_daily_metrics


def test_db_error_before_status_assigned_raises_runtime_error_not_unbound_local():
    log_calls = []

    def fake_log(*args):
        log_calls.append(args)

    with patch("algo.orchestrator.phase9_reconciliation.DatabaseContext") as mock_ctx:
        mock_ctx.return_value.__enter__.side_effect = psycopg2.OperationalError("connection lost")

        with pytest.raises(RuntimeError, match="Failed to persist metrics"):
            _update_daily_metrics(date(2026, 7, 27), fake_log)

    # finally must still run and log something usable, not crash on unassigned locals
    assert log_calls
    assert log_calls[0][0] == 9
    assert log_calls[0][1] == "metrics_update"
