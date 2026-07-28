"""Regression test: monitor_data_staleness.py must not report a table FRESH when its
most recent load attempt actually failed.

get_table_age_minutes() only measures when a row was last touched (MAX(updated_at)), which
can't distinguish a real, successful refresh from a crashed run that only wrote a handful of
rows before dying (e.g. lock contention against a concurrent backfill). Confirmed live
2026-07-28: price_daily's data_loader_status row showed status='failed',
completion_pct=0.00, symbols_loaded=1 of 5471 (a genuine loader crash under contention from
6 concurrent fundamentals backfills) - yet because that single row happened to include
today's date, updated_at looked recent enough for check_all_tables() to report a plain
green "FRESH", hiding a load that had essentially not happened. Since CLAUDE.md directs
operators to this exact script for stale-data diagnosis, a false-fresh reading here defeats
its entire purpose.

Fixed by cross-checking data_loader_status.status (which always reflects the outcome of the
most recent attempt - a later successful retry overwrites 'failed' back to 'ok'/'HEALTHY')
in addition to raw timestamp age.
"""

from unittest.mock import MagicMock, patch

from scripts import monitor_data_staleness as mds


class TestFailedLoadNotMaskedAsFresh:
    def test_recently_touched_but_failed_load_reports_critical_not_fresh(self):
        # A crashed run wrote one row moments ago - age alone reads as very fresh.
        with (
            patch.object(mds, "get_table_age_minutes", return_value=5.0),
            patch.object(mds, "get_loader_failed", return_value=True),
        ):
            results = mds.check_all_tables()

        assert results["price_daily"]["level"] == "critical"
        assert "FAILED" in results["price_daily"]["status"]

    def test_recently_touched_and_successful_load_still_reports_fresh(self):
        with (
            patch.object(mds, "get_table_age_minutes", return_value=5.0),
            patch.object(mds, "get_loader_failed", return_value=False),
        ):
            results = mds.check_all_tables()

        assert results["price_daily"]["level"] == "ok"

    def test_get_loader_failed_reads_current_status_from_data_loader_status(self):
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = ("failed",)
        mock_db_ctx = MagicMock()
        mock_db_ctx.__enter__.return_value = mock_cursor

        with patch.object(mds, "DatabaseContext", return_value=mock_db_ctx):
            assert mds.get_loader_failed("price_daily") is True

        executed_sql = mock_cursor.execute.call_args[0][0]
        assert "data_loader_status" in executed_sql

    def test_get_loader_failed_false_for_healthy_status(self):
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = ("HEALTHY",)
        mock_db_ctx = MagicMock()
        mock_db_ctx.__enter__.return_value = mock_cursor

        with patch.object(mds, "DatabaseContext", return_value=mock_db_ctx):
            assert mds.get_loader_failed("growth_metrics") is False

    def test_get_loader_failed_false_when_table_not_tracked(self):
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_db_ctx = MagicMock()
        mock_db_ctx.__enter__.return_value = mock_cursor

        with patch.object(mds, "DatabaseContext", return_value=mock_db_ctx):
            assert mds.get_loader_failed("some_untracked_table") is False


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
