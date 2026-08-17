"""Regression test: /api/algo/freshness/extended's loader_health block used one flat
90-minute "is this RUNNING table actively running or stuck" threshold for every table,
regardless of that table's own real configured timeout (loaders/loader_timeout_config.py).

Real per-loader timeouts range from ~10min (naaim/aaii) to 1440min/24h (price_daily, per
that config's yfinance rate-limiting margin) - a perfectly healthy price_daily or
company_info_sec (540min/9h) run past 90 minutes was being counted as "unhealthy" here, and
flagged "TIMEOUT RISK" in dashboard/panels/health.py's mirrored (now also fixed) check,
despite having used only a fraction of its real budget. This is the same anti-pattern
already fixed in reap_stale_running_loaders() and fix_loader_status_drift.py's original
flat 30-min check.

Fixed: both checks now look up each table's own configured timeout via get_loader_timeout(),
falling back to the old 90-minute default only for an unregistered table.
"""

import sys
from datetime import datetime, timedelta, timezone
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


def test_long_timeout_loader_past_90min_is_not_flagged_unhealthy():
    # price_daily is configured for 1440min (24h) - 3 hours in is nowhere near stuck.
    started_3h_ago = datetime.now(timezone.utc) - timedelta(hours=3)
    data = _run(
        [
            {
                "table_name": "price_daily",
                "status": "RUNNING",
                "consecutive_failures": 0,
                "retry_count": 0,
                "last_success_at": None,
                "execution_started": started_3h_ago,
                "execution_completed": None,
                "completion_pct": 40,
            }
        ]
    )

    assert data["loader_health"] == []
    assert data["loader_health_total_unhealthy"] == 0


def test_short_timeout_loader_past_its_own_budget_is_still_flagged_unhealthy():
    # market_sentiment is configured for 15min - 3 hours in is genuinely stuck. (Not naaim -
    # that's excluded from this endpoint's tracking entirely via PIPELINE_REMOVED_TABLES,
    # unrelated to the timeout logic under test here.)
    started_3h_ago = datetime.now(timezone.utc) - timedelta(hours=3)
    data = _run(
        [
            {
                "table_name": "market_sentiment",
                "status": "RUNNING",
                "consecutive_failures": 0,
                "retry_count": 0,
                "last_success_at": None,
                "execution_started": started_3h_ago,
                "execution_completed": None,
                "completion_pct": 40,
            }
        ]
    )

    table_names = {lh["table_name"] for lh in data["loader_health"]}
    assert table_names == {"market_sentiment"}
    assert data["loader_health_total_unhealthy"] == 1


def test_unregistered_table_falls_back_to_90min_default():
    # A table with no entry in loader_timeout_config.py must not crash - falls back to the
    # old flat 90-minute default rather than raising.
    started_2h_ago = datetime.now(timezone.utc) - timedelta(hours=2)
    data = _run(
        [
            {
                "table_name": "not_a_real_registered_table_xyz",
                "status": "RUNNING",
                "consecutive_failures": 0,
                "retry_count": 0,
                "last_success_at": None,
                "execution_started": started_2h_ago,
                "execution_completed": None,
                "completion_pct": 40,
            }
        ]
    )

    table_names = {lh["table_name"] for lh in data["loader_health"]}
    assert table_names == {"not_a_real_registered_table_xyz"}
    assert data["loader_health_total_unhealthy"] == 1
