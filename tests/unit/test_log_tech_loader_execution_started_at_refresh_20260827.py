"""Regression test for the 2026-08-27 fix: load_technical_indicators.py's data_loader_runs
INSERT ... ON CONFLICT DO UPDATE omitted started_at from the UPDATE SET clause, so a retried
loader on the same run_date kept whatever started_at the FIRST attempt that day had, while
completed_at kept advancing to NOW() on every retry - making completed_at - started_at balloon
to hours even when the loader's own measured duration_seconds was seconds.

Same bug class, same table, as the 2026-08-19 fix in load_prices.py's log_loader_execution()
(see test_log_loader_execution_started_at_refresh.py) - found independently in this second,
separate implementation via an ON CONFLICT column-gap sweep across every loader in the repo.

Fixed by extracting the inline logging block into _log_tech_loader_execution() (making it
directly testable) and recomputing started_at as NOW() - duration_seconds on every write.
"""

from unittest.mock import MagicMock, patch

import psycopg2

from loaders.load_technical_indicators import _log_tech_loader_execution


class TestLogTechLoaderExecutionStartedAtRefresh:
    def test_started_at_recomputed_from_this_runs_duration_on_every_write(self) -> None:
        cur = MagicMock()
        loader = MagicMock()
        loader._get_required_duration.return_value = 42.3
        result = {"rows_inserted": 5000}

        with patch("loaders.load_technical_indicators.DatabaseContext") as mock_ctx:
            mock_ctx.return_value.__enter__.return_value = cur
            _log_tech_loader_execution("completed", result, loader)

        assert cur.execute.call_count == 1
        sql, params = cur.execute.call_args.args

        # started_at must be recomputed on every UPDATE, not left stale from a prior attempt.
        assert "started_at = EXCLUDED.started_at" in sql

        # started_at is derived from this run's own duration, not a bare NOW().
        assert "NOW() - (%s * interval '1 second')" in sql

        # duration_seconds is passed twice: once for the started_at interval calc, once for
        # the duration_seconds column itself.
        assert params.count(42.3) == 2

    def test_failed_run_also_refreshes_started_at(self) -> None:
        cur = MagicMock()
        loader = MagicMock()
        loader._get_required_duration.return_value = 7.1
        result = {"rows_inserted": 0}

        with patch("loaders.load_technical_indicators.DatabaseContext") as mock_ctx:
            mock_ctx.return_value.__enter__.return_value = cur
            _log_tech_loader_execution("failed", result, loader)

        sql, params = cur.execute.call_args.args
        assert "started_at = EXCLUDED.started_at" in sql
        assert params.count(7.1) == 2

    def test_logging_failure_is_swallowed_non_critical(self) -> None:
        loader = MagicMock()
        loader._get_required_duration.return_value = 1.0
        result = {"rows_inserted": 1}

        with patch("loaders.load_technical_indicators.DatabaseContext") as mock_ctx:
            mock_ctx.return_value.__enter__.side_effect = psycopg2.OperationalError("db down")
            # Should not raise - logging failures are non-critical per the surrounding try/except.
            _log_tech_loader_execution("completed", result, loader)
