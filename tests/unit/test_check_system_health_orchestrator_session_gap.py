"""Regression test: check_system_health.py's Orchestrator Status check used a flat
120-minute staleness threshold, ignoring the real 4-session production schedule
(morning 9:30, afternoon 13:00, preclose 15:00, evening 17:30 ET - see
scripts/orchestrator_scheduler.py's TRADING_SESSIONS).

Bug: every evening after the 5:30 PM evening run, and before next trading day's
9:30 AM morning run, the last run's age climbs well past 120 minutes even though
no further session is due until the next morning - a false [WARN] confirmed live
2026-07-27 at 21:35 ET (146 min after the 5:30 PM run, no run overdue).

Fixed via `_most_recently_due_orchestrator_session(now_et)`: walks back through the
real session schedule (across weekends/holidays via MarketCalendar) to find the most
recently-due session, and only flags stale if the latest run predates that session
by more than a grace buffer.
"""

from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import check_system_health as csh

ET = ZoneInfo("America/New_York")


class TestMostRecentlyDueOrchestratorSession:
    def test_evening_gap_is_not_flagged_as_an_overdue_session(self):
        # 9:00 PM ET on a trading day, well after the 5:30 PM evening session - the
        # evening session itself is the most recently due one, not tomorrow morning's.
        now_et = datetime(2026, 7, 27, 21, 0, tzinfo=ET)

        with patch(
            "algo.infrastructure.market_calendar.MarketCalendar.is_trading_day",
            return_value=True,
        ):
            due = csh._most_recently_due_orchestrator_session(now_et)

        assert due == datetime(2026, 7, 27, 17, 30, tzinfo=ET)

    def test_before_market_open_falls_back_to_previous_trading_days_evening_session(self):
        # 8:00 AM ET, before today's 9:30 AM morning session has even happened yet -
        # the most recently due session is still the previous trading day's evening one.
        now_et = datetime(2026, 7, 27, 8, 0, tzinfo=ET)

        with patch(
            "algo.infrastructure.market_calendar.MarketCalendar.is_trading_day",
            side_effect=lambda d: d != datetime(2026, 7, 27).date(),
        ):
            due = csh._most_recently_due_orchestrator_session(now_et)

        assert due == datetime(2026, 7, 26, 17, 30, tzinfo=ET)

    def test_mid_afternoon_uses_the_most_recent_intraday_session(self):
        # 2:00 PM ET - afternoon (1:00 PM) has fired, preclose (3:00 PM) hasn't yet.
        now_et = datetime(2026, 7, 27, 14, 0, tzinfo=ET)

        with patch(
            "algo.infrastructure.market_calendar.MarketCalendar.is_trading_day",
            return_value=True,
        ):
            due = csh._most_recently_due_orchestrator_session(now_et)

        assert due == datetime(2026, 7, 27, 13, 0, tzinfo=ET)


class TestCheckOrchestratorEveningGapNotAFalseWarn:
    @staticmethod
    def _run_check_orchestrator(age_minutes, now_et, is_trading_day_side_effect=None):
        fake_cur = type("FakeCursor", (), {
            "execute": lambda self, *a, **k: None,
            "fetchone": lambda self: (54, None, 1, age_minutes),
        })()
        fake_conn = type("FakeConn", (), {
            "cursor": lambda self: fake_cur,
            "close": lambda self: None,
        })()

        with (
            patch("psycopg2.connect", return_value=fake_conn),
            patch.object(csh, "_get_db_credentials", return_value={
                "host": "x", "port": 5432, "user": "x", "password": "x", "name": "x",
            }),
            patch(
                "algo.infrastructure.market_calendar.MarketCalendar.is_trading_day",
                side_effect=is_trading_day_side_effect if is_trading_day_side_effect else (lambda d: True),
            ),
        ):
            # now_et is injected directly (check_orchestrator's own optional param) rather
            # than patched, since it does a function-local `from datetime import datetime`
            # that a module-level patch("check_system_health.datetime") can't intercept.
            return csh.check_orchestrator(now_et=now_et)

    def test_146_minutes_after_evening_run_is_ok_not_warn(self):
        # Reproduces the exact live false-positive: 146 min since last run, current time
        # 9:35 PM ET (well after the 5:30 PM evening session, nothing else due tonight).
        now_et = datetime(2026, 7, 27, 21, 35, tzinfo=ET)
        result = self._run_check_orchestrator(age_minutes=146.0, now_et=now_et)

        assert result["status"] == "OK"
        assert any("[OK] Latest run: 146 minutes ago" in d for d in result["details"])

    def test_genuinely_missed_session_still_warns(self):
        # 2:30 PM ET, afternoon session (1:00 PM) was due 90 min ago but the last actual
        # run was 200 min ago - the afternoon session was missed entirely, must WARN.
        now_et = datetime(2026, 7, 27, 14, 30, tzinfo=ET)
        result = self._run_check_orchestrator(age_minutes=200.0, now_et=now_et)

        assert result["status"] == "WARN"
        assert any("stale" in d for d in result["details"])
