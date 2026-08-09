"""Regression test for a silent-fail-open bug in
_check_and_refresh_local()'s _check_data_completeness() helper
(algo/orchestrator/phase1_failsafe_retry.py):

When a table's MAX(date) was fresh but the *completeness* check query itself hit a
DB or data error, the helper returned (True, "") - "complete" - which silently
skipped refreshing a table this failsafe could not actually verify. That is the
same fail-open-and-treat-as-fine shape this codebase's governance rules forbid
elsewhere (loaders/*.py's COALESCE/fabricated-default fixes). This is a failsafe
retry module: an unverifiable table should fail *closed* (treated as incomplete,
triggering a - cheap - refresh) rather than silently passing the check.
"""

import psycopg2
import pytest

from algo.orchestrator.phase1_failsafe_retry import _check_and_refresh_local


class _FakeCursor:
    """MAX(date)/MAX(updated_at) queries always return today (never stale), so every
    table falls through to the completeness check - which raises, exercising the
    fixed error path."""

    def __init__(self, expected_date):
        self._expected_date = expected_date
        self._last_query = ""

    def execute(self, query, params=None):
        self._last_query = query
        if "COUNT(*)" in query:
            raise psycopg2.DatabaseError("simulated completeness-check DB error")

    def fetchone(self):
        assert "COUNT(*)" not in self._last_query
        return (self._expected_date,)


class _FakeDatabaseContext:
    def __init__(self, expected_date):
        self._cur = _FakeCursor(expected_date)

    def __enter__(self):
        return self._cur

    def __exit__(self, *exc):
        return False


class TestCompletenessCheckFailsClosed:
    def test_completeness_check_db_error_marks_table_incomplete_not_skipped(self, monkeypatch):
        from algo.orchestrator import phase1_failsafe_retry as mod

        expected_date = mod._get_expected_data_date()[0]
        monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _FakeDatabaseContext(expected_date))

        results = _check_and_refresh_local(dry_run=True)

        # Every configured table had a fresh MAX(date) but an unverifiable completeness
        # check - all must be flagged incomplete (fail closed), not silently accepted.
        assert set(results["incomplete_loaders"]) == {
            "price_daily",
            "technical_data_daily",
            "stock_scores",
            "buy_sell_daily",
            "market_health_daily",
            "trend_template_data",
            # Session 81 fix: earnings_calendar added to the failsafe retry table set
            # (fixes the earnings-blackout staleness gap) - this fixed set predates that fix.
            "earnings_calendar",
        }
