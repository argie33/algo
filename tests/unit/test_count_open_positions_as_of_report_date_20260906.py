"""Regression test: DailyFinanceReport._count_open_positions must count positions
open AS OF report_date, not positions that are currently open.

Bug (found 2026-09-06, real-money-readiness audit): this used to filter on the
position's CURRENT status = 'open', not its status as-of report_date.
DailyFinanceReport.generate() explicitly accepts a historical report_date (used for
reprocessing/backfill). For a backdated report, a position that was open ON
report_date but has since closed would be silently excluded (current status='closed'),
understating the historical open-position count for that date - a misattribution
across time, not a same-day bug.

Fixed: count positions created on/before report_date that are either still open
(closed_at IS NULL) or closed strictly after report_date.
"""

from datetime import date
from unittest.mock import MagicMock

from algo.reporting.daily_report import DailyFinanceReport


def _make_generator():
    return object.__new__(DailyFinanceReport)


def test_query_does_not_filter_on_current_status():
    """The bug's root cause: filtering on status='open' reflects TODAY's status, not
    the position's status as-of report_date."""
    gen = _make_generator()
    cur = MagicMock()
    cur.fetchone.return_value = (3,)

    gen._count_open_positions(cur, date(2026, 8, 1))

    query = cur.execute.call_args.args[0]
    assert "status = 'open'" not in query, (
        "must not filter on current status='open' - a position open on report_date but "
        "since closed would be wrongly excluded from a historical report"
    )


def test_query_includes_positions_still_open_or_closed_after_report_date():
    gen = _make_generator()
    cur = MagicMock()
    cur.fetchone.return_value = (3,)

    gen._count_open_positions(cur, date(2026, 8, 1))

    query = cur.execute.call_args.args[0]
    assert "closed_at IS NULL" in query
    assert "closed_at::date > %s" in query
    assert "created_at <= %s" in query


def test_params_bind_report_date_for_both_bounds():
    gen = _make_generator()
    cur = MagicMock()
    cur.fetchone.return_value = (3,)
    report_date = date(2026, 8, 1)

    gen._count_open_positions(cur, report_date)

    params = cur.execute.call_args.args[1]
    assert params == (report_date, report_date)
