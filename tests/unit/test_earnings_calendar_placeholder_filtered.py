"""Regression test: earnings-proximity checks must exclude data_unavailable placeholder rows.

load_earnings_calendar.py's _unavailable_record() stamps earnings_date=today (the fetch-attempt
date, not a real earnings date) whenever a symbol's yfinance fetch fails outright (RuntimeError)
or has no coverage. Before this fix, two consumers queried earnings_calendar for "earnings
within N days" without excluding these placeholder rows, so a same-day fetch failure looked
identical to "this symbol reports earnings today":

- algo/orchestrator/phase8_preentry_health_check.py::_check_earnings_in_3d - a hard, non-votable
  entry gate. Live-reproduced 2026-08-09: a single mass yfinance fetch-failure event wrote 4918
  placeholder rows dated 2026-08-08, and every candidate touching one was rejected regardless of
  its real earnings schedule (several had real, confirmed earnings dates days in the past that
  were nowhere near the 0-3 day window - the rejection was driven entirely by the phantom row).
- algo/monitoring/position_monitor.py::_days_to_earnings - feeds the EARNINGS_IN_0D/1D/2D/3D exit
  flag. An unfiltered phantom "today" row silently defeated this function's own documented
  "raise ValueError -> caller gracefully skips the earnings flag" contract for missing data,
  instead returning 0 days and risking a false-positive forced exit on a healthy open position.

Narrowing _check_earnings_in_3d to real dates is safe because it is independently backstopped by
pretrade_checks.py's EarningsBlackout re-check (algo/risk/earnings_blackout.py), which
deliberately stays fail-closed on data_unavailable rows right before order placement - seeded by
a real prior-session incident (see earnings_blackout_data_unavailable_critical_bug memory). That
backstop is untouched by this fix.
"""

from unittest.mock import MagicMock, patch

from algo.orchestrator.phase8_preentry_health_check import _check_earnings_in_3d


class _RecordingCursor:
    def __init__(self, fetchone_result):
        self.queries = []
        self._fetchone_result = fetchone_result

    def execute(self, sql, params=None):
        self.queries.append(sql)

    def fetchone(self):
        return self._fetchone_result


def _db_context(cursor):
    mock_ctx = MagicMock()
    mock_ctx.__enter__.return_value = cursor
    mock_ctx.__exit__.return_value = False
    return mock_ctx


_MODULE = "algo.orchestrator.phase8_preentry_health_check"


def test_check_earnings_in_3d_excludes_data_unavailable_rows():
    cursor = _RecordingCursor(fetchone_result=(0,))
    with patch(f"{_MODULE}.DatabaseContext", return_value=_db_context(cursor)):
        _check_earnings_in_3d("AAPL", "2026-08-07")

    assert len(cursor.queries) == 1
    sql = cursor.queries[0]
    assert "data_unavailable" in sql, (
        "earnings-in-3d query must exclude data_unavailable placeholder rows "
        "(load_earnings_calendar.py stamps earnings_date=today on any fetch failure)"
    )


def test_position_monitor_days_to_earnings_excludes_data_unavailable_rows():
    import algo.monitoring.position_monitor as pm_module

    monitor = pm_module.PositionMonitor.__new__(pm_module.PositionMonitor)
    cursor = _RecordingCursor(fetchone_result=None)

    with __import__("pytest").raises(ValueError):
        monitor._days_to_earnings("AAPL", __import__("datetime").date(2026, 8, 7), cur=cursor)

    assert len(cursor.queries) == 1
    sql = cursor.queries[0]
    assert "data_unavailable" in sql, (
        "_days_to_earnings query must exclude data_unavailable placeholder rows so a same-day "
        "fetch failure can't masquerade as a real earnings date and force a false exit flag"
    )
