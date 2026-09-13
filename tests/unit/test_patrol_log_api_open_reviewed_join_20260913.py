"""Regression: /api/algo/patrol-log (_get_patrol_log) must match the CLI backlog tool's
logic - open findings only, joined to any human triage decision - not a raw, undeduped,
unfiltered scan of the entire historical log.

BUG (found 2026-09-13, goal session: "make sure the react site has all the data-health
insights we need"): the query was `SELECT * FROM data_patrol_log ORDER BY created_at DESC
LIMIT/OFFSET` with no `status = 'open'` filter and no join to data_patrol_review - the exact
"re-logged every run, functionally invisible, no triage state" problem
scripts/data_patrol_backlog_report.py's 2026-09-09 fix addressed for the CLI, left unfixed on
the API/React side. The "Recent Patrol Findings" panel could show stale/superseded rows and
gave no way to tell a genuinely-open finding from one a human already reviewed as acceptable.
"""

import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "lambda" / "api"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def test_patrol_log_query_filters_to_open_status():
    from routes.algo_handlers.monitoring import _get_patrol_log

    cursor = Mock()
    cursor.fetchone.return_value = {"total": 2}
    cursor.fetchall.return_value = [
        {
            "created_at": datetime(2026, 9, 13, 12, 0, 0),
            "check_name": "revenue_yoy_magnitude_jump",
            "severity": "warn",
            "target_table": "annual_income_statement",
            "message": "59 symbol/year(s) show a >20x YoY swing",
            "patrol_run_id": "run-1",
            "review_status": "acceptable",
            "review_note": "Review queue by design - real M&A/divestiture swings",
            "reviewed_at": datetime(2026, 9, 10, 0, 0, 0),
        },
        {
            "created_at": datetime(2026, 9, 13, 11, 0, 0),
            "check_name": "quarterly_stock_based_compensation_nonnegative",
            "severity": "warn",
            "target_table": "quarterly_cash_flow",
            "message": "1 symbol/quarter(s) have negative stock_based_compensation",
            "patrol_run_id": "run-1",
            "review_status": None,
            "review_note": None,
            "reviewed_at": None,
        },
    ]

    response = _get_patrol_log(cursor, limit=50, offset=0)

    count_sql = cursor.execute.call_args_list[0].args[0]
    assert "status = 'open'" in count_sql

    findings_sql = cursor.execute.call_args_list[1].args[0]
    assert "status = 'open'" in findings_sql
    assert "data_patrol_review" in findings_sql

    assert response["statusCode"] == 200
    findings = response["data"]["items"]
    assert findings[0]["review_status"] == "acceptable"
    assert findings[1].get("review_status") is None


def test_patrol_log_count_matches_open_only_total():
    from routes.algo_handlers.monitoring import _get_patrol_log

    cursor = Mock()
    cursor.fetchone.return_value = {"total": 5}
    cursor.fetchall.return_value = []

    response = _get_patrol_log(cursor, limit=50, offset=0)

    assert response["data"]["total"] == 5
