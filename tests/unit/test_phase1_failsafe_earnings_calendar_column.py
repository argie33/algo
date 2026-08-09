"""Regression test: _check_and_refresh_local() querying MAX(date) FROM earnings_calendar.

earnings_calendar has no `date` column (only `earnings_date`, which is forward-looking -
future announcement dates, not a load timestamp - so freshness must be tracked via
`updated_at`, same as stock_scores). The generic freshness-check loop in
_check_and_refresh_local() special-cased only stock_scores for this, so the
earnings_calendar entry added in Session 81 (specifically to fix the earnings-blackout
staleness gap) always raised psycopg2.errors.UndefinedColumn, which was silently caught
and logged as a warning - meaning earnings_calendar staleness could never actually be
detected or trigger a refresh. Confirmed live via a real orchestrator run before the fix.
"""

from algo.orchestrator.phase1_failsafe_retry import _check_and_refresh_local


class _RecordingCursor:
    """Records every query issued and returns a fresh timestamp for all of them,
    so every table falls through past the freshness check with no need to also
    fake the completeness-check query."""

    def __init__(self, expected_date):
        self._expected_date = expected_date
        self.queries = []

    def execute(self, query, params=None):
        self.queries.append(query)

    def fetchone(self):
        last = self.queries[-1]
        if "COUNT(*)" in last:
            return (1, 1)
        import datetime

        return (datetime.datetime.combine(self._expected_date, datetime.time()),)


class _RecordingDatabaseContext:
    def __init__(self, cursor):
        self._cur = cursor

    def __enter__(self):
        return self._cur

    def __exit__(self, *exc):
        return False


class TestEarningsCalendarFreshnessColumn:
    def test_earnings_calendar_queried_by_updated_at_not_date(self, monkeypatch):
        from algo.orchestrator import phase1_failsafe_retry as mod

        expected_date = mod._get_expected_data_date()[0]
        cursor = _RecordingCursor(expected_date)
        monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _RecordingDatabaseContext(cursor))

        _check_and_refresh_local(dry_run=True)

        earnings_queries = [q for q in cursor.queries if "earnings_calendar" in q and "MAX(" in q]
        assert earnings_queries, "expected a MAX(...) freshness query against earnings_calendar"
        for q in earnings_queries:
            assert "MAX(updated_at)" in q, f"earnings_calendar must be queried via updated_at, not date: {q!r}"
            assert "MAX(date)" not in q, f"earnings_calendar has no `date` column: {q!r}"
