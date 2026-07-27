"""Regression coverage for lambda/api/routes/algo_handlers/metrics.py's
_compute_data_age_seconds() - the new helper backing performance panel freshness
display (report_date/data_age_seconds on the perf and perf_anl endpoints).

Mirrors the existing DB-side-NOW()-vs-app-clock pattern already used for the portfolio
panel's data_age_seconds (see that function's own docstring for the "always 0/always
stale" incident this avoids) - here applied to algo_performance_daily.updated_at.
"""

import importlib
from datetime import datetime, timezone

import pytest

metrics_module = importlib.import_module("lambda.api.routes.algo_handlers.metrics")
_compute_data_age_seconds = metrics_module._compute_data_age_seconds


class _FakeCursor:
    def __init__(self, now_value):
        self._now_value = now_value
        self.executed = []

    def execute(self, sql, *args):
        self.executed.append(sql)

    def fetchone(self):
        return {"now": self._now_value}


class TestComputeDataAgeSeconds:
    def test_computes_age_from_db_side_now_not_app_clock(self):
        last_write_at = datetime(2026, 7, 27, 12, 0, 0)
        db_now = datetime(2026, 7, 27, 12, 5, 0)  # 5 minutes later
        cur = _FakeCursor(db_now)

        age = _compute_data_age_seconds(cur, last_write_at, "algo_performance_daily")

        assert age == 300
        assert cur.executed == ["SELECT NOW()::timestamp"]

    def test_strips_tzinfo_before_subtracting_mixed_naive_and_aware(self):
        last_write_at = datetime(2026, 7, 27, 12, 0, 0, tzinfo=timezone.utc)
        db_now = datetime(2026, 7, 27, 12, 1, 0)  # naive, as psycopg2 returns for TIMESTAMP
        cur = _FakeCursor(db_now)

        age = _compute_data_age_seconds(cur, last_write_at, "algo_performance_daily")

        assert age == 60

    def test_missing_timestamp_fails_fast_instead_of_reporting_zero(self):
        cur = _FakeCursor(datetime(2026, 7, 27, 12, 0, 0))

        with pytest.raises(RuntimeError, match="missing timestamp"):
            _compute_data_age_seconds(cur, None, "algo_performance_daily")

        assert cur.executed == [], "must not even query NOW() when there's nothing to compare against"

    def test_empty_now_row_fails_fast(self):
        class _EmptyCursor(_FakeCursor):
            def fetchone(self):
                return None

        cur = _EmptyCursor(None)

        with pytest.raises(RuntimeError, match="NOW\\(\\) returned empty"):
            _compute_data_age_seconds(cur, datetime(2026, 7, 27, 12, 0, 0), "algo_performance_daily")
