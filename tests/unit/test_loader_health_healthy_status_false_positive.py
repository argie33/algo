"""Regression test: /api/algo/freshness/extended's loader_health block previously flagged
perfectly healthy loaders as "unhealthy" whenever data_loader_status.status held anything
other than the literal string "COMPLETED".

data_loader_status.status is written by two competing vocabularies that share the same
column (see utils/loader_infrastructure.py's update_loader_status docstring and
algo/monitoring/pipeline_health.py's HealthStatus sweep): the loader's own execution result
(COMPLETED/FAILED/success/OK) and pipeline_health.py's unconditional per-run freshness sweep
(HEALTHY/STALE/VERY_STALE/MISSING/ERROR/DEPRECATED), which overwrites the same column for
every tracked table on every orchestrator run. Confirmed live 2026-08-03: the dashboard's
"Loader Issues" section listed tables like aaii_sentiment/algo_audit_log/algo_config as
issues with "status: HEALTHY" - the naive `status != "COMPLETED"` check treated the
freshness sweep's own "all clear" value as a failure.

lambda/api/routes/algo_handlers/monitoring.py::_get_orchestrator_history_extended must
recognize COMPLETED/success/OK/ok/HEALTHY/DEPRECATED as healthy, and must not silently
truncate the real unhealthy count before computing it (the old `ORDER BY
consecutive_failures DESC ... LIMIT 30` could drop a genuinely-unhealthy table sitting at
0 consecutive_failures, e.g. STALE, once more than ~30 tables are tracked).
"""

import sys
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "lambda" / "api"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def _run(loader_rows):
    from routes.algo_handlers.monitoring import _get_orchestrator_history_extended

    cursor = Mock()
    cursor.fetchall.side_effect = [
        [],  # run_history
        [],  # phase_health stats
        [],  # failure_patterns
        loader_rows,  # data_loader_status
    ]
    cursor.fetchone.side_effect = [
        {"total_7d": 0, "successful_7d": 0},
        {"total_30d": 0, "successful_30d": 0},
    ]

    response = _get_orchestrator_history_extended(cursor, params={})
    return response["data"]


def test_healthy_and_deprecated_statuses_are_not_flagged_unhealthy():
    # Table names deliberately avoid PIPELINE_REMOVED_TABLES (e.g. aaii_sentiment,
    # sec_dividends) - that exclusion is tested separately in
    # test_loader_health_pipeline_removed_tables_excluded.py, and mixing the two concerns
    # into one table made this test's total_tracked assertion break whenever the shared
    # exclusion list changed for reasons unrelated to the HEALTHY/DEPRECATED status check.
    data = _run([
        {"table_name": "technical_data_daily", "status": "HEALTHY", "consecutive_failures": 0,
         "retry_count": 0, "last_success_at": None, "execution_completed": None, "completion_pct": 100},
        {"table_name": "algo_metrics_daily", "status": "DEPRECATED", "consecutive_failures": 0,
         "retry_count": 0, "last_success_at": None, "execution_completed": None, "completion_pct": None},
        {"table_name": "price_daily", "status": "COMPLETED", "consecutive_failures": 0,
         "retry_count": 0, "last_success_at": None, "execution_completed": None, "completion_pct": 100},
    ])

    assert data["loader_health"] == []
    assert data["loader_health_total_unhealthy"] == 0
    assert data["loader_health_total_tracked"] == 3


def test_genuine_failures_are_still_flagged_unhealthy():
    data = _run([
        {"table_name": "company_info_sec", "status": "RUNNING", "consecutive_failures": 1,
         "retry_count": 1, "last_success_at": None, "execution_completed": None, "completion_pct": 50},
        {"table_name": "technical_data_daily", "status": "HEALTHY", "consecutive_failures": 0,
         "retry_count": 0, "last_success_at": None, "execution_completed": None, "completion_pct": 100},
    ])

    table_names = {lh["table_name"] for lh in data["loader_health"]}
    assert table_names == {"company_info_sec"}
    assert data["loader_health_total_unhealthy"] == 1
    assert data["loader_health_total_tracked"] == 2
