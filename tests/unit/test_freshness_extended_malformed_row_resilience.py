"""Regression test: /api/algo/freshness/extended must not 500 the entire dashboard response
because one row in run_history/phase_health/loader_health is malformed.

Live-observed 2026-08-03 14:50-14:55 ET: this endpoint returned a bare
`TypeError: int() argument must be a string, a bytes-like object or a real number, not
'list'` wrapped as a generic 400 "Invalid request" for ~5 minutes of the TUI dashboard's
periodic polling, then stopped recurring - the exact triggering row/state was never
reproduced (scanned orchestrator_execution_log.phase_results and data_loader_status for the
whole failure window afterward, found nothing malformed still present). Whatever caused it,
the underlying design flaw is real and independent of the exact trigger: a single bad row
anywhere in this handler's three per-row loops (run_history, phase_health, loader_health)
took the *entire* endpoint down instead of being skipped, because none of those loops had
per-row error isolation - any TypeError/AttributeError while processing one row propagated
out of the whole function and got caught by the outer db_route_handler as an opaque
"Invalid request", telling neither the operator which row nor which field was at fault.

lambda/api/routes/algo_handlers/monitoring.py::_get_orchestrator_history_extended now wraps
each loop body in its own try/except, logs the offending row_id/error, and continues -
one corrupt row degrades that one row out of the response instead of failing the dashboard's
extended health view for everyone.
"""

import sys
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "lambda" / "api"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def _run(run_rows=None, phase_rows=None, failure_rows=None, loader_rows=None):
    from routes.algo_handlers.monitoring import _get_orchestrator_history_extended

    cursor = Mock()
    cursor.fetchall.side_effect = [
        run_rows or [],
        phase_rows or [],
        failure_rows or [],
        loader_rows or [],
    ]
    cursor.fetchone.side_effect = [
        {"total_7d": 0, "successful_7d": 0},
        {"total_30d": 0, "successful_30d": 0},
    ]

    response = _get_orchestrator_history_extended(cursor, params={})
    return response


def test_malformed_run_history_row_is_skipped_not_fatal():
    good_row = {
        "run_id": "LOCAL-MORNING-20260804-090000-000000",
        "run_date": "2026-08-04",
        "overall_status": "ok",
        "halt_reason": None,
        "started_at": "2026-08-04T09:00:00",
        "completed_at": "2026-08-04T09:05:00",
        "phase_results": [{"phase": "1", "status": "ok"}],
        "phases_completed": 9,
        "phases_halted": 0,
        "phases_errored": 0,
    }
    # Malformed: phase_results holding non-dict entries (e.g. a corrupted/legacy write)
    # instead of the {"phase": ..., "status": ...} shape every reader assumes.
    bad_row = {
        "run_id": "LOCAL-BAD-ROW",
        "run_date": "2026-08-04",
        "overall_status": "ok",
        "halt_reason": None,
        "started_at": "2026-08-04T08:00:00",
        "completed_at": "2026-08-04T08:05:00",
        "phase_results": [["not", "a", "dict"]],
        "phases_completed": 9,
        "phases_halted": 0,
        "phases_errored": 0,
    }

    response = _run(run_rows=[good_row, bad_row])

    assert response["statusCode"] == 200
    run_ids = [r["run_id"] for r in response["data"]["run_history"]]
    assert "LOCAL-MORNING-20260804-090000-000000" in run_ids


def test_malformed_loader_health_row_does_not_fail_whole_endpoint():
    good_row = {
        "table_name": "price_daily",
        "status": "COMPLETED",
        "consecutive_failures": 0,
        "retry_count": 0,
        "last_success_at": None,
        "execution_completed": None,
        "completion_pct": 100,
    }
    # Malformed: consecutive_failures as a non-numeric type (defensive case - the real
    # historical trigger was never pinned down, but this exercises the same failure shape:
    # a comparison/arithmetic op on a field that's normally always an int).
    bad_row = {
        "table_name": "corrupted_table",
        "status": "COMPLETED",
        "consecutive_failures": ["bad"],
        "retry_count": 0,
        "last_success_at": None,
        "execution_completed": None,
        "completion_pct": 100,
    }

    response = _run(loader_rows=[good_row, bad_row])

    assert response["statusCode"] == 200
    # good_row is healthy so contributes nothing to loader_health; bad_row's error is
    # swallowed per-row rather than 500ing the response - total_tracked still counts both.
    assert response["data"]["loader_health_total_tracked"] == 2
