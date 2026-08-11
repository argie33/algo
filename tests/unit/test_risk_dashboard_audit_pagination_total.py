"""Regression test: risk-dashboard audit endpoints must report the TRUE row count for
the requested window, not just the size of the LIMIT 100 page returned.

Live-verified 2026-08-04: algo_position_sizing_audit had 495 rows in the trailing 30
days. /api/algo/risk-dashboard/position-sizing-audit (and the sibling stop-loss-audit
endpoint) queried `... ORDER BY created_at DESC LIMIT 100` and called
`list_response(items)` with no `total`, so list_response fell back to `total =
len(items) == 100` - silently reporting "100 total" when 495 rows actually existed in
the window, with no signal to the caller that ~80% of the window was dropped.

Fix: both queries now select `COUNT(*) OVER() AS total_count` alongside the LIMIT 100
page, and pass that true count through to `list_response(items, total=total_count,
limit=100)` so truncation is visible instead of silent.
"""

import sys
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "lambda" / "api"))
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def _sizing_audit_row(total_count: int) -> dict:
    return {
        "symbol": "AAPL",
        "signal_date": None,
        "entry_price": 150.0,
        "stop_loss_price": 145.0,
        "base_shares": 100,
        "final_shares": 80,
        "position_size_pct": 0.05,
        "cascade_multiplier": 0.8,
        "reasons_json": None,
        "created_at": None,
        "total_count": total_count,
    }


def _stop_loss_row(total_count: int) -> dict:
    return {
        "symbol": "AAPL",
        "signal_date": None,
        "entry_price": 150.0,
        "stop_loss_price": 145.0,
        "distance_pct": 3.3,
        "stop_method": "atr",
        "stop_reasoning": "2x ATR below entry",
        "candidates_json": None,
        "created_at": None,
        "total_count": total_count,
    }


def test_position_sizing_audit_reports_true_total_not_page_size():
    from routes.risk_dashboard import _get_position_sizing_audit

    # 495 real rows in the window, only 100 fit in the LIMIT 100 page.
    page = [_sizing_audit_row(495) for _ in range(100)]
    cursor = Mock()
    cursor.execute = Mock()
    cursor.fetchall = Mock(return_value=page)

    response = _get_position_sizing_audit(cursor, days=30)

    assert len(response["data"]["items"]) == 100
    assert response["data"]["total"] == 495, (
        "total must reflect the true window count (495), not len(items) (100) - "
        "reporting 100 here silently hides that 395 rows were dropped"
    )
    assert response["data"]["limit"] == 100


def test_position_sizing_audit_total_matches_page_when_under_limit():
    # Sanity check: when the window has fewer rows than LIMIT 100, total must still
    # equal the true count (not artificially inflated or deflated).
    from routes.risk_dashboard import _get_position_sizing_audit

    page = [_sizing_audit_row(7) for _ in range(7)]
    cursor = Mock()
    cursor.execute = Mock()
    cursor.fetchall = Mock(return_value=page)

    response = _get_position_sizing_audit(cursor, days=30)

    assert len(response["data"]["items"]) == 7
    assert response["data"]["total"] == 7


def test_stop_loss_audit_reports_true_total_not_page_size():
    from routes.risk_dashboard import _get_stop_loss_audit

    page = [_stop_loss_row(250) for _ in range(100)]
    cursor = Mock()
    cursor.execute = Mock()
    cursor.fetchall = Mock(return_value=page)

    response = _get_stop_loss_audit(cursor, days=30)

    assert len(response["data"]["items"]) == 100
    assert response["data"]["total"] == 250, "total must reflect the true window count (250), not len(items) (100)"
    assert response["data"]["limit"] == 100
