"""Regression test: check_system_health.py's own weekend/holiday-gap-aware
staleness threshold must actually cover stock_scores, not just
price_daily/technical_data_daily/market_exposure_daily.

Bug: the gap-aware threshold block's comment explicitly claims "consistent
with monitor_data_staleness.py" (which applies gap-awareness to stock_scores,
growth_metrics, quality_metrics, value_metrics, algo_trades, algo_positions),
but the actual `if table_name in (...)` tuple omitted stock_scores - even
though stock_scores is one of the 5 tables this same function checks. Result:
every Monday morning (or the morning after any holiday), a stock_scores row
written Friday evening reads as 24+ hours stale under the flat 24h threshold
and this tool reports a false [WARN], even though monitor_data_staleness.py
(the more precise tool) correctly reports it FRESH. Confirmed live 2026-07-27
(a Monday): real DB had stock_scores at 24.5h - just over the flat 24h bar.

Also regression-covers the module-level sys.stdout TextIOWrapper Windows-
encoding-fix bug already fixed in monitor_data_staleness.py and
verify_eventbridge_scheduler.py: importing this module must not corrupt
pytest's own capture streams (this test file itself is the proof - if the fix
regressed, collecting/running this file would crash pytest's capture
teardown with "ValueError: I/O operation on closed file").
"""

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import check_system_health as csh


class FakeCursor:
    """Returns one canned row per table, in check_database's own dict order:
    price_daily, stock_scores, algo_orchestrator_runs, market_exposure_daily,
    technical_data_daily.
    """

    def __init__(self, ages_by_order):
        self._ages = iter(ages_by_order)
        self._current_age = None

    def execute(self, *args, **kwargs):
        self._current_age = next(self._ages)

    def fetchone(self):
        return (100, None, self._current_age)


def _run_check_database_with_gap(gap_days: int, stock_scores_age_hours: float) -> dict:
    fake_cur = FakeCursor(
        [
            1.0,  # price_daily: fresh regardless, not what this test targets
            stock_scores_age_hours,  # stock_scores: the field under test
            0.1,  # algo_orchestrator_runs: fresh
            1.0,  # market_exposure_daily: fresh
            1.0,  # technical_data_daily: fresh
        ]
    )
    fake_conn = MagicMock()
    fake_conn.cursor.return_value = fake_cur

    today = date.today()
    prev_trading_day = today - timedelta(days=gap_days)

    with (
        patch("psycopg2.connect", return_value=fake_conn),
        patch.object(csh, "_get_db_credentials", return_value={
            "host": "x", "port": 5432, "user": "x", "password": "x", "name": "x",
        }),
        patch(
            "algo.infrastructure.market_calendar.MarketCalendar.is_trading_day",
            return_value=True,
        ),
        patch(
            "algo.infrastructure.market_calendar.MarketCalendar.get_previous_trading_day",
            return_value=prev_trading_day,
        ),
    ):
        return csh.check_database()


class TestStockScoresGetsGapAwareThreshold:
    def test_stock_scores_24_5h_after_a_weekend_gap_is_not_a_false_warn(self):
        # A 3-calendar-day gap (Friday -> Monday), stock_scores last updated 24.5h
        # ago - just past the flat 24h bar but well within the 24h + one-trading-
        # day-lag gap-adjusted bar (96h). Must read as fresh, not WARN.
        result = _run_check_database_with_gap(gap_days=3, stock_scores_age_hours=24.5)

        stock_scores_line = next(d for d in result["details"] if "stock_scores" in d)
        assert "[OK]" in stock_scores_line, (
            f"stock_scores falsely flagged stale across a weekend gap: {stock_scores_line}"
        )
        assert result["status"] == "OK"

    def test_stock_scores_genuinely_stuck_still_warns(self):
        # No gap (gap_days=1, i.e. yesterday was a trading day) and stock_scores
        # is 30h stale - a real stuck loader, must still WARN.
        result = _run_check_database_with_gap(gap_days=1, stock_scores_age_hours=30.0)

        stock_scores_line = next(d for d in result["details"] if "stock_scores" in d)
        assert "[WARN]" in stock_scores_line
        assert result["status"] == "WARN"
