"""Regression test for a live-reproduced bug in ValueAtRisk.concentration_report()
(algo/risk/var.py): the "portfolio_value" field was `round(portfolio_value, 2)` where
portfolio_value is a Decimal - Python's round() returns a Decimal when given a Decimal, not a
float, unlike every other numeric field in this function's return dict (all of which round an
already-float value). Live-confirmed: json.dumps() on the real function's return value crashed
with "TypeError: Object of type Decimal is not JSON serializable" - any API endpoint or
dashboard fetch consuming concentration_report()'s output would 500. The sibling function in
the same file, beta_exposure(), already gets this right via float(portfolio_value...).
"""

import json
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

from algo.risk.var import ValueAtRisk


class _FakeCursor:
    """Sequential fetchall/fetchone stand-in matching concentration_report()'s query order:
    1. positions list (fetchall)
    2. portfolio snapshot row (fetchone)
    """

    def __init__(self, position_rows, snapshot_row):
        self._position_rows = position_rows
        self._snapshot_row = snapshot_row
        self._fetchall_called = False

    def execute(self, query, *args, **kwargs):
        pass

    def fetchall(self):
        self._fetchall_called = True
        return self._position_rows

    def fetchone(self):
        return self._snapshot_row


def _make_calculator():
    return ValueAtRisk({})


def test_concentration_report_portfolio_value_is_json_serializable():
    today = datetime.now(timezone.utc).astimezone().date()
    position_rows = [
        ("AAPL", Decimal("10"), Decimal("150.00"), "Technology", "Consumer Electronics"),
        ("MSFT", Decimal("5"), Decimal("300.00"), "Technology", "Software"),
    ]
    snapshot_row = (Decimal("50000.00"), today)

    fake_cursor = _FakeCursor(position_rows, snapshot_row)
    fake_ctx = MagicMock()
    fake_ctx.__enter__ = MagicMock(return_value=fake_cursor)
    fake_ctx.__exit__ = MagicMock(return_value=False)

    calculator = _make_calculator()

    with (
        patch("algo.risk.var.DatabaseContext", return_value=fake_ctx),
        patch("algo.infrastructure.MarketCalendar.is_trading_day", return_value=True),
    ):
        result = calculator.concentration_report()

    assert isinstance(result["portfolio_value"], float)
    # Must not raise - this is the actual live-reproduced failure mode.
    json.dumps(result)
