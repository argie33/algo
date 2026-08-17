"""Regression test: /api/algo/freshness/extended's loader_health detail list must
prioritize the most-stale tables when truncating to 15, not raw consecutive_failures.

Live-confirmed 2026-08-17 (via /goal): stability_metrics was FAILED with only 1
consecutive_failure but last_success_at 2026-08-13 (4 days stale, a direct algo score
input) - ORDER BY consecutive_failures DESC in the SQL fetch meant 32 other tables with
a higher raw failure count (many just 2, some retried once more on an unrelated transient
blip) all sorted ahead of it, so it silently never appeared in the truncated top-15 detail
list shown on the dashboard - even though loader_health_total_unhealthy correctly counted
it. A human reading the dashboard's "Loader errors" list would never see the table that
had actually been broken the longest.

lambda/api/routes/algo_handlers/monitoring.py::_get_orchestrator_history_extended now
re-sorts loader_health by staleness (oldest last_success_at first, never-succeeded oldest
of all) before truncating.
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "lambda" / "api"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def _run(loader_rows):
    from routes.algo_handlers.monitoring import _get_orchestrator_history_extended

    import utils.db.timezone_utils as timezone_utils

    original_tz_cache = timezone_utils._DB_TZ_CACHE
    timezone_utils._DB_TZ_CACHE = ZoneInfo("UTC")
    try:
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
    finally:
        timezone_utils._DB_TZ_CACHE = original_tz_cache


def _row(table_name, consecutive_failures, last_success_at):
    return {
        "table_name": table_name,
        "status": "FAILED",
        "consecutive_failures": consecutive_failures,
        "retry_count": 0,
        "last_success_at": last_success_at,
        "execution_started": None,
        "execution_completed": None,
        "completion_pct": 0,
    }


def test_stale_low_failure_table_survives_truncation_over_high_failure_recent_tables():
    now = datetime.now(timezone.utc)
    stale_but_low_failures = _row("stability_metrics", 1, now - timedelta(days=4))
    # 20 tables with a higher raw failure count but a recent last_success_at - under the
    # old ORDER BY consecutive_failures DESC these would all outrank stability_metrics.
    noisy_recent_failures = [_row(f"noisy_table_{i}", 2, now - timedelta(hours=1)) for i in range(20)]

    data = _run([stale_but_low_failures, *noisy_recent_failures])

    table_names = [lh["table_name"] for lh in data["loader_health"]]
    assert "stability_metrics" in table_names
    assert data["loader_health_total_unhealthy"] == 21


def test_never_succeeded_table_sorts_first():
    now = datetime.now(timezone.utc)
    never_succeeded = _row("never_succeeded_table", 2, None)
    recently_failed = [_row(f"recent_{i}", 2, now - timedelta(hours=1)) for i in range(5)]

    data = _run([never_succeeded, *recently_failed])

    assert data["loader_health"][0]["table_name"] == "never_succeeded_table"
