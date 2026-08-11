"""Regression test for a bug in _check_and_refresh_local()'s completeness check.

Bug (found 2026-08-10): stock_scores/earnings_calendar track freshness via `updated_at` (a
loader-run timestamp), not a `date` column representing the trading day the data is for. The
staleness check correctly treats a same-day-or-later `updated_at` as "not stale" (it's ahead
of, not behind, expected_data_date). But the completeness check that runs immediately after
used `expected_data_date` (the historical trading day, e.g. yesterday in a MORNING/INTRADAY
context) as the date to query for, instead of the table's own actual latest date
(table_max_date, e.g. today). Since a same-day refresh's `updated_at` is always today, `COUNT(*)
WHERE updated_at::date = expected_data_date` was always 0 - permanently reporting "No rows for
{expected_data_date}" and re-triggering a full reload on every single MORNING/INTRADAY
orchestrator run (in production: every real 2am ET morning cron), even seconds after a fresh,
100%-complete refresh.

Live-reproduced today across 3 consecutive local orchestrator runs (morning/afternoon/preclose,
all classified MORNING/INTRADAY context): stock_scores was retriggered for refresh every single
time despite being freshly and completely loaded moments before.
"""

import datetime

from algo.orchestrator.phase1_failsafe_retry import _check_and_refresh_local


class _RecordingCursor:
    """MAX(date)/MAX(updated_at) always returns TODAY (simulating a same-day refresh) while
    expected_data_date (INTRADAY context) is yesterday - table_max_date != expected_data_date,
    the exact scenario the buggy code collapsed. COUNT(*) queries only return a row when the
    date parameter passed matches table_max_date (today) - reproducing "no rows exist for
    expected_data_date" while real, complete data exists for today.
    """

    def __init__(self, today: datetime.date):
        self._today = today
        self.completeness_queries: list[tuple[str, tuple]] = []

    def execute(self, query, params=None):
        self._last_query = query
        self._last_params = params or ()
        if "COUNT(*)" in query:
            self.completeness_queries.append((query, self._last_params))

    def fetchone(self):
        if "COUNT(*)" in self._last_query:
            queried_date = self._last_params[0] if self._last_params else None
            if queried_date == self._today:
                return (100, 100)  # fully populated for today
            return (0, 0)  # nothing for any other date, including expected_data_date
        return (datetime.datetime.combine(self._today, datetime.time()),)


class _RecordingDatabaseContext:
    def __init__(self, cursor):
        self._cur = cursor

    def __enter__(self):
        return self._cur

    def __exit__(self, *exc):
        return False


class TestCompletenessChecksActualLatestDateNotExpectedDate:
    def test_stock_scores_same_day_refresh_not_flagged_sparse_in_intraday_context(self, monkeypatch):
        from algo.orchestrator import phase1_failsafe_retry as mod

        today = datetime.date(2026, 8, 10)
        cursor = _RecordingCursor(today)
        monkeypatch.setattr(mod, "DatabaseContext", lambda *a, **kw: _RecordingDatabaseContext(cursor))
        # Force an INTRADAY context so expected_data_date (previous trading day) != today,
        # reproducing the exact mismatch that triggered the bug.
        monkeypatch.setattr(
            mod, "_get_expected_data_date", lambda **kwargs: (datetime.date(2026, 8, 7), "INTRADAY - test")
        )

        result = _check_and_refresh_local(run_date=today, pipeline_context="MORNING", dry_run=True)

        assert "stock_scores" not in result["incomplete_loaders"], (
            "stock_scores was refreshed today (table_max_date=today, fully complete) but got "
            "flagged incomplete because the completeness check queried for expected_data_date "
            "(2026-08-07) instead of the table's own actual latest date (today)"
        )

        stock_scores_completeness_queries = [(q, p) for q, p in cursor.completeness_queries if "stock_scores" in q]
        assert stock_scores_completeness_queries, "expected a completeness COUNT(*) query against stock_scores"
        for _, params in stock_scores_completeness_queries:
            assert today in params, (
                f"completeness check must query using the table's actual latest date ({today}), "
                f"not expected_data_date (2026-08-07): params={params}"
            )
