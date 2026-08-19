"""Regression test for the 2026-08-19 fix: log_loader_execution()'s INSERT ... ON CONFLICT
DO UPDATE into data_loader_runs omitted started_at from the UPDATE SET clause, so a retried
loader on the same run_date kept whatever started_at the FIRST attempt that day had, while
completed_at kept advancing to NOW() on every retry - making completed_at - started_at balloon
to hours even when the loader's own measured duration_seconds was seconds.

Live-confirmed on price_daily (loader-health review, 2026-08-19): a run with
duration_seconds=39.59 showed completed_at - started_at of 1h36m in data_loader_runs, because
an earlier same-day attempt's started_at was never refreshed on the later upsert.

Fixed by recomputing started_at as NOW() - duration_seconds on every write (INSERT and
UPDATE), so it always reflects the current run's own start time.
"""

from unittest.mock import MagicMock, patch

from loaders.load_prices import log_loader_execution


class TestLogLoaderExecutionStartedAtRefresh:
    def test_started_at_recomputed_from_this_runs_duration_on_every_write(self) -> None:
        cur = MagicMock()

        with patch("loaders.load_prices.DatabaseContext") as mock_ctx:
            mock_ctx.return_value.__enter__.return_value = cur
            log_loader_execution(
                loader_name="price_daily",
                table_name="price_daily",
                status="completed",
                records_loaded=278893,
                duration_seconds=39.59,
            )

        assert cur.execute.call_count == 1
        sql, params = cur.execute.call_args.args

        # started_at must be recomputed on every UPDATE, not left stale from a prior attempt.
        assert "started_at = EXCLUDED.started_at" in sql

        # started_at is derived from this run's own duration, not a bare NOW().
        assert "NOW() - (%s * interval '1 second')" in sql

        # duration_seconds is passed twice: once for the started_at interval calc, once for
        # the duration_seconds column itself.
        assert params.count(39.59) == 2

    def test_failed_run_also_refreshes_started_at(self) -> None:
        cur = MagicMock()

        with patch("loaders.load_prices.DatabaseContext") as mock_ctx:
            mock_ctx.return_value.__enter__.return_value = cur
            log_loader_execution(
                loader_name="price_daily",
                table_name="price_daily",
                status="failed",
                error_msg="Market close data unavailable after 5 consecutive failures.",
                duration_seconds=14.6,
            )

        sql, params = cur.execute.call_args.args
        assert "started_at = EXCLUDED.started_at" in sql
        assert params.count(14.6) == 2
