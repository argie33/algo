"""Regression test for a live-reproduced bug in ValueAtRisk.beta_exposure()/
concentration_report() (algo/risk/var.py): generate_daily_risk_report(report_date) accepted
a caller-supplied report date (Phase 9 passes its run_date) but never threaded it down into
either method's snapshot-freshness check - both hardcoded `today = datetime.now(EASTERN_TZ).date()`
regardless of what report_date was passed in.

Live-reproduced via three local `--date 2026-08-21` orchestrator test runs (2026-08-23 13:11,
2026-08-23 14:22, 2026-08-24 07:17 per algo_audit_log): reconciliation correctly wrote/found the
2026-08-21 snapshot every time (status=success, identical $73,364.58 portfolio value each run -
proof nothing was actually broken), but this freshness check then compared that correct
snapshot_date against real wall-clock "today" (2026-08-23/24) instead of the run_date under
test, raising "[VAR CRITICAL] Portfolio snapshot is stale ... requires manual clear" and
halting Phase 9 with a governance halt that misrepresented a working reconciliation as broken.

Fixed by threading report_date through beta_exposure(report_date)/concentration_report(report_date)
and using it (falling back to real wall-clock today only when the caller passes None, preserving
existing behavior for normal live same-day calls).
"""

import json
from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch

from algo.risk.var import ValueAtRisk


class _FakeCursor:
    """Sequential fetchall/fetchone stand-in matching beta_exposure()/concentration_report()'s
    query order: 1. positions list (fetchall), 2. portfolio snapshot row (fetchone)."""

    def __init__(self, position_rows, snapshot_row):
        self._position_rows = position_rows
        self._snapshot_row = snapshot_row

    def execute(self, query, *args, **kwargs):
        pass

    def fetchall(self):
        return self._position_rows

    def fetchone(self):
        return self._snapshot_row


def _make_calculator():
    return ValueAtRisk({})


def test_concentration_report_uses_report_date_not_real_today():
    # A historical Friday, replayed days later (Monday) - exactly the local `--date` test
    # workflow documented in CLAUDE.md's "--date does NOT bypass the market-hours guard" note.
    historical_friday = date(2026, 8, 21)
    position_rows = [
        ("AAPL", Decimal("10"), Decimal("150.00"), "Technology", "Consumer Electronics"),
    ]
    snapshot_row = (Decimal("50000.00"), historical_friday)

    fake_cursor = _FakeCursor(position_rows, snapshot_row)
    fake_ctx = MagicMock()
    fake_ctx.__enter__ = MagicMock(return_value=fake_cursor)
    fake_ctx.__exit__ = MagicMock(return_value=False)

    calculator = _make_calculator()

    with (
        patch("algo.risk.var.DatabaseContext", return_value=fake_ctx),
        patch("algo.infrastructure.MarketCalendar.is_trading_day", return_value=True),
    ):
        # Must not raise "Portfolio snapshot is stale" - the snapshot matches report_date
        # even though real wall-clock today is several days later.
        result = calculator.concentration_report(report_date=historical_friday)

    assert isinstance(result["portfolio_value"], float)
    json.dumps(result)


def test_beta_exposure_still_rejects_genuinely_stale_snapshot_for_report_date():
    """Sanity check: the fix must not disable the staleness check entirely - a snapshot that
    is actually stale RELATIVE TO report_date must still raise."""
    report_date = date(2026, 8, 24)
    stale_snapshot_date = report_date - timedelta(days=5)
    position_rows = [
        ("AAPL", Decimal("10"), Decimal("150.00"), Decimal("140.00")),
    ]
    snapshot_row = (Decimal("50000.00"), stale_snapshot_date)

    fake_cursor = _FakeCursor(position_rows, snapshot_row)
    fake_ctx = MagicMock()
    fake_ctx.__enter__ = MagicMock(return_value=fake_cursor)
    fake_ctx.__exit__ = MagicMock(return_value=False)

    calculator = _make_calculator()

    with (
        patch("algo.risk.var.DatabaseContext", return_value=fake_ctx),
        patch("algo.infrastructure.MarketCalendar.is_trading_day", return_value=True),
    ):
        try:
            calculator.beta_exposure(report_date=report_date)
            raised = False
        except RuntimeError as e:
            raised = "stale" in str(e).lower()
    assert raised
