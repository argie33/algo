"""Regression test: /api/algo/freshness/extended's loader_health summary must not count
tables that PIPELINE_REMOVED_TABLES (lambda/api/routes/algo_handlers/market.py) excludes
from the DATA FRESHNESS table, and must not flag a loader that's actively mid-run as
unhealthy.

Live-confirmed 2026-08-04 (via /goal): the dashboard showed "Loader Health: 3 table(s)
with issues (see Data Freshness Table below)" while the Data Freshness Table itself showed
no issues. Root cause, live-verified against data_loader_status:
  - algo_untracked_positions (status=MISSING) is in PIPELINE_REMOVED_TABLES, so
    market.py's _get_data_status() can never show it - yet monitoring.py's loader_health
    query had no such exclusion and counted it anyway, pointing the summary at a table the
    freshness grid structurally cannot contain.
  - dividend_data (status=RUNNING, 91% complete, started minutes earlier) was actively
    loading normally - the freshness grid already renders that as benign "Loading now:"
    progress, not an issue, but loader_health flagged any non-whitelisted status
    (including RUNNING) as unhealthy regardless of how long it had been running.

lambda/api/routes/algo_handlers/monitoring.py::_get_orchestrator_history_extended now
skips PIPELINE_REMOVED_TABLES and treats RUNNING as healthy while under the same 90-minute
threshold dashboard/panels/health.py's own "TIMEOUT RISK" flag uses.
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

    # Bypass get_db_timezone()'s real DB round-trip (SHOW timezone via DatabaseContext) -
    # same pattern as test_stock_scores_staleness_timezone.py. All timestamps in this file
    # are already UTC-aware, so the actual DB session timezone is irrelevant here.
    #
    # FIXED 2026-08-04: _DB_TZ_CACHE is a process-global singleton (utils/db/timezone_utils.py
    # caches it forever once set, by design - real DB session timezone doesn't change mid-
    # process). Overwriting it here with no restore permanently poisoned every later test in
    # the same pytest process that relies on get_db_timezone() querying ITS OWN mock - live-
    # confirmed this broke test_market_exposure_weights.py's
    # test_uses_real_session_timezone_not_hardcoded_eastern whenever this file ran first in
    # the same process (passes in isolation, fails deterministically as part of a larger
    # run). Save/restore instead of leaking the override past this test module.
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


def test_pipeline_removed_table_never_counted_as_unhealthy():
    data = _run(
        [
            {
                "table_name": "algo_untracked_positions",
                "status": "MISSING",
                "consecutive_failures": 0,
                "retry_count": 0,
                "last_success_at": None,
                "execution_started": None,
                "execution_completed": None,
                "completion_pct": 100,
            },
            {
                "table_name": "price_daily",
                "status": "COMPLETED",
                "consecutive_failures": 0,
                "retry_count": 0,
                "last_success_at": None,
                "execution_started": None,
                "execution_completed": None,
                "completion_pct": 100,
            },
        ]
    )

    table_names = {lh["table_name"] for lh in data["loader_health"]}
    assert "algo_untracked_positions" not in table_names
    assert data["loader_health_total_unhealthy"] == 0
    # Only price_daily is trackable - algo_untracked_positions is excluded entirely, not
    # merely marked healthy, so it must not inflate the tracked denominator either.
    assert data["loader_health_total_tracked"] == 1


def test_recently_started_running_loader_not_flagged_unhealthy():
    # A real DB cursor returns datetime objects (not ISO strings) for timestamp columns -
    # normalize_to_utc_datetime only accepts date/datetime/None, so the mock must match.
    started_10_min_ago = datetime.now(timezone.utc) - timedelta(minutes=10)
    data = _run(
        [
            {
                "table_name": "dividend_data",
                "status": "RUNNING",
                "consecutive_failures": 0,
                "retry_count": 0,
                "last_success_at": None,
                "execution_started": started_10_min_ago,
                "execution_completed": None,
                "completion_pct": 91,
            },
        ]
    )

    assert data["loader_health"] == []
    assert data["loader_health_total_unhealthy"] == 0


def test_stuck_running_loader_past_90_minutes_is_flagged_unhealthy():
    started_2_hours_ago = datetime.now(timezone.utc) - timedelta(hours=2)
    data = _run(
        [
            {
                "table_name": "dividend_data",
                "status": "RUNNING",
                "consecutive_failures": 0,
                "retry_count": 0,
                "last_success_at": None,
                "execution_started": started_2_hours_ago,
                "execution_completed": None,
                "completion_pct": 12,
            },
        ]
    )

    table_names = {lh["table_name"] for lh in data["loader_health"]}
    assert table_names == {"dividend_data"}
    assert data["loader_health_total_unhealthy"] == 1
