"""Regression: /api/algo/last-run and /api/algo/freshness/extended must return
timezone-aware started_at/completed_at strings, not offset-less naive ones.

BUG (live-observed 2026-08-17): algo_orchestrator_runs.started_at/completed_at are naive
`timestamp without time zone` columns written in UTC (confirmed via `SHOW timezone`).
_get_last_run and _get_orchestrator_history_extended serialized them with
safe_json_serialize(), which calls .isoformat() on a naive datetime with no tzinfo attached
-> an offset-less ISO string like "2026-08-17T19:15:17.969215". Every downstream consumer
(dashboard/formatter_strategies.py's DataAgeFormatter) then has to guess a zone for that
string and assumed Eastern - silently mislabeling a UTC timestamp and shifting its computed
age by the ET/UTC offset. A run that started 39 minutes ago rendered as "-202m ago" in the
dashboard's orchestrator-run panel.

Fix: normalize_to_utc_datetime() is applied to started_at/completed_at before
safe_json_serialize() stringifies them, so the emitted ISO string always carries an explicit
UTC offset ("+00:00") that any downstream consumer can parse unambiguously.
"""

import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "lambda" / "api"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def test_get_last_run_started_at_carries_explicit_utc_offset():
    from routes.algo_handlers.monitoring import _get_last_run

    cursor = Mock()
    cursor.fetchone.return_value = {
        "run_id": "LOCAL-PRECLOSE-20260817-151517-857415",
        "run_date": "2026-08-17",
        "overall_status": "halted",
        "halt_reason": "[PHASE 7 CRITICAL HALT] stock_scores loader's own status is 'FAILED'",
        # Naive datetime, exactly what psycopg2 hands back for a `timestamp without
        # time zone` column - no tzinfo attached, but the DB session is UTC.
        "started_at": datetime(2026, 8, 17, 19, 15, 17, 969215),
        "completed_at": datetime(2026, 8, 17, 19, 15, 55, 522785),
        "phase_results": None,
        "phases_completed": 6,
    }

    response = _get_last_run(cursor)

    assert response["statusCode"] == 200
    started_at = response["data"]["started_at"]
    completed_at = response["data"]["completed_at"]
    assert started_at.endswith(("+00:00", "Z")), (
        f"started_at must carry an explicit UTC offset so downstream age formatters "
        f"can't mis-guess its timezone, got {started_at!r}"
    )
    assert completed_at.endswith(("+00:00", "Z"))


def test_orchestrator_history_extended_run_history_started_at_carries_utc_offset():
    from routes.algo_handlers.monitoring import _get_orchestrator_history_extended

    cursor = Mock()
    cursor.fetchall.side_effect = [
        [
            {
                "run_id": "LOCAL-MORNING-20260817-090000-000000",
                "run_date": "2026-08-17",
                "overall_status": "ok",
                "halt_reason": None,
                # Naive datetime, exactly what psycopg2 hands back for a `timestamp
                # without time zone` column - no tzinfo attached, DB session is UTC.
                "started_at": datetime(2026, 8, 17, 9, 0, 0),
                "completed_at": datetime(2026, 8, 17, 9, 5, 0),
                "phase_results": [{"phase": "1", "status": "ok"}],
                "phases_completed": 9,
                "phases_halted": 0,
                "phases_errored": 0,
            }
        ],
        [],
        [],
        [],
    ]
    cursor.fetchone.side_effect = [
        {"total_7d": 1, "successful_7d": 1},
        {"total_30d": 1, "successful_30d": 1},
    ]

    response = _get_orchestrator_history_extended(cursor, params={})

    assert response["statusCode"] == 200
    run = response["data"]["run_history"][0]
    assert run["started_at"].endswith(("+00:00", "Z"))
    assert run["completed_at"].endswith(("+00:00", "Z"))
