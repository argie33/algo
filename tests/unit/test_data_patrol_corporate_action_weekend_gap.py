"""Regression test for the 2026-08-11 fix: PriceSanityChecker.check_corporate_actions()
required the LAG'd previous row to be exactly 1 CALENDAR day before the current row
(`date = prev_date + 1 day`). LAG(...) OVER (PARTITION BY symbol ORDER BY date) already
returns each symbol's true immediately-preceding row regardless of weekends, holidays, or
per-symbol data gaps - the extra filter then silently discarded every comparison that crossed
a weekend/holiday (Friday->Monday, 3 calendar days apart), the exact pattern already fixed
elsewhere in data_patrol (quality.py's zero/volume checks) for the same root cause. Live-
verified: on a Monday's real data, 7 symbols had a genuine >30% Friday-to-Monday close drop
that this filter excluded entirely - a real corporate-action/data-integrity signal silently
never surfacing on the first trading day after every weekend or holiday.
"""

import inspect

from algo.monitoring.data_patrol.checks.price_sanity import PriceSanityChecker


class TestCorporateActionWeekendGap:
    def test_check_corporate_actions_does_not_require_exact_calendar_day_gap(self):
        source = inspect.getsource(PriceSanityChecker.check_corporate_actions)
        sql_start = source.index("cur.execute(")
        sql = source[sql_start:]
        assert "prev_date +" not in sql, (
            "must not filter on `date = prev_date + 1 day` - LAG's own window-function "
            "ordering already handles trading-day/data-gap adjacency correctly, and this "
            "filter silently excludes every weekend/holiday-crossing comparison"
        )
        assert "LAG(" in sql, "must still use LAG to find each symbol's true previous row"
