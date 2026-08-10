"""Regression test for the 2026-08-10 fix: loaders/load_prices.py's derive_aggregate_prices()
called LoaderStatusManager.mark_completed() without ever calling mark_running()/
update_progress() first, and without passing the run's own symbols_loaded/symbol_count.

mark_completed()'s safety check then fell back to reading symbol_count/symbols_loaded from
the DB row - which this bulk-SQL derivation never populates at all (it's not a per-symbol
loop). Live-confirmed: symbols_loaded stuck at 0 while symbol_count held a stale value from
an unrelated prior run (10594 for price_weekly/price_monthly, 19 for the etf equivalents), so
every single derivation - success or not - computed 0% completion and got marked FAILED, even
though the upsert genuinely succeeded (latest_date was correctly set to the current period).

Fixed by passing the run's own real upserted-row count (cur.rowcount) as both loaded/total
(100% by construction - a single atomic SQL statement has no partial-failure concept) with
min_completion_pct=0.0 (also covers the legitimate 0-new-rows case).
"""

from unittest.mock import MagicMock, patch

from loaders.load_prices import derive_aggregate_prices


def _mock_db_context(rowcount: int, max_date: object) -> MagicMock:
    cur = MagicMock()
    cur.rowcount = rowcount
    cur.fetchone.return_value = (max_date,)
    ctx = MagicMock()
    ctx.__enter__.return_value = cur
    ctx.__exit__.return_value = False
    return ctx


class TestDeriveAggregatePricesReportsRealCompletion:
    def test_successful_derivation_marks_completed_not_failed(self) -> None:
        mock_status_mgr = MagicMock()
        with (
            patch("loaders.load_prices.DatabaseContext", return_value=_mock_db_context(4917, None)),
            patch("loaders.load_prices.LoaderStatusManager", return_value=mock_status_mgr),
        ):
            derive_aggregate_prices("stock")

        assert mock_status_mgr.mark_completed.call_count == 2  # weekly + monthly
        for call in mock_status_mgr.mark_completed.call_args_list:
            assert call.kwargs["current_run_symbols_loaded"] == call.kwargs["current_run_symbol_count"]
            assert call.kwargs["current_run_symbols_loaded"] == 4917
            assert call.kwargs["min_completion_pct"] == 0.0

    def test_zero_new_rows_still_marks_completed_not_failed(self) -> None:
        """No new daily bars since the last derivation (already up to date) must not be
        treated as a failure - it's the correct, expected steady state."""
        mock_status_mgr = MagicMock()
        with (
            patch("loaders.load_prices.DatabaseContext", return_value=_mock_db_context(0, None)),
            patch("loaders.load_prices.LoaderStatusManager", return_value=mock_status_mgr),
        ):
            derive_aggregate_prices("etf")

        for call in mock_status_mgr.mark_completed.call_args_list:
            assert call.kwargs["current_run_symbols_loaded"] == 0
            assert call.kwargs["current_run_symbol_count"] == 0
            assert call.kwargs["min_completion_pct"] == 0.0
