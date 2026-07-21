"""Regression tests for the portfolio summary API endpoint.

_get_portfolio_summary (lambda/api/routes/algo_handlers/metrics.py) used
`round(x, 2) if x else None` for total_value/cash/invested/daily_change/
daily_change_percent - Python truthiness treats 0.0 as falsy, so a fully
invested account (cash=$0.00), an all-cash account (invested=$0.00), or a
flat trading day (daily_return_pct=0.00%) were silently reported as "N/A"
on the headline portfolio summary instead of their real (zero) value.

'lambda' is a Python keyword, so the module under test is loaded via
importlib rather than a normal `from lambda...` import.
"""

import importlib
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
metrics_module = importlib.import_module("lambda.api.routes.algo_handlers.metrics")


def _mock_cursor(row: dict) -> MagicMock:
    cur = MagicMock()
    cur.fetchone.return_value = row
    return cur


def test_portfolio_summary_reports_zero_cash_not_none():
    """Fully invested account: cash=$0.00 must show 0.0, not None."""
    row = {
        "total_portfolio_value": 100000.0,
        "total_cash": 0.0,
        "total_equity": 100000.0,
        "position_count": 5,
        "daily_return_pct": 0.0,
    }
    with patch.object(metrics_module, "safe_dict_convert", side_effect=lambda r: r):
        response = metrics_module._get_portfolio_summary(_mock_cursor(row))

    body = response["data"] if "data" in response else response
    assert body["cash"] == 0.0
    assert body["cash"] is not None
    assert body["daily_change_percent"] == 0.0
    assert body["daily_change_percent"] is not None
    assert body["daily_change"] == 0.0
    assert body["daily_change"] is not None


def test_portfolio_summary_reports_zero_invested_not_none():
    """All-cash account: invested=$0.00 must show 0.0, not None."""
    row = {
        "total_portfolio_value": 50000.0,
        "total_cash": 50000.0,
        "total_equity": 0.0,
        "position_count": 0,
        "daily_return_pct": 0.0,
    }
    with patch.object(metrics_module, "safe_dict_convert", side_effect=lambda r: r):
        response = metrics_module._get_portfolio_summary(_mock_cursor(row))

    body = response["data"] if "data" in response else response
    assert body["invested"] == 0.0
    assert body["invested"] is not None
