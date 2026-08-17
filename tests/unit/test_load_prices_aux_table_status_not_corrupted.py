"""Regression test for the 2026-08-17 fix: PriceLoader._update_loader_status()'s "SESSION
112/113" secondary layer, which defensively marks price_daily's 5 auxiliary output tables
(price_weekly/monthly, etf_price_daily/weekly/monthly) COMPLETED, passed THIS (stock) run's
own current_run_symbols_loaded/current_run_symbol_count (e.g. 4886/4925) straight through to
every aux table's mark_completed() call - even though etf_price_daily/weekly/monthly track a
completely different, ~5-symbol universe.

Live-confirmed: this wrote symbols_loaded=4886 into etf_price_daily's data_loader_status row,
which then made the REAL etf loader's own next update_progress(symbols_loaded=5) call fail
StatusManager's monotonic "cannot decrease" guard (5 < 4886), a silent STATUS_MANAGER error
that corrupted the dashboard's ETF progress tracking on every price_daily run.

Fixed by not passing the stock run's counts to the aux tables at all - mark_completed() falls
back to reading each aux table's own last-known counts instead.
"""

from unittest.mock import MagicMock, patch

from loaders.load_prices import PriceLoader

AUX_TABLES = [
    "price_weekly",
    "price_monthly",
    "etf_price_daily",
    "etf_price_weekly",
    "etf_price_monthly",
]


def _make_loader():
    loader = PriceLoader.__new__(PriceLoader)
    loader.table_name = "price_daily"
    loader.interval = "1d"
    loader._stats = {"symbols_total": 4925, "symbols_processed": 4886, "start_time": 1_700_000_000.0}
    return loader


class TestAuxTableStatusNotCorruptedByPrimaryCounts:
    def test_aux_tables_do_not_receive_stock_run_counts(self):
        loader = _make_loader()
        cur = MagicMock()
        # 1st DatabaseContext("read"): COUNT(*), MAX(date) from price_daily
        # 2nd DatabaseContext("read"): COUNT(DISTINCT symbol) verification query
        cur.fetchone.side_effect = [(4925, "2026-08-17"), (4886,)]

        with (
            patch("loaders.load_prices.DatabaseContext") as mock_ctx,
            patch("loaders.load_prices._invalidate_phase1_cache"),
            patch("loaders.load_prices.LoaderStatusManager") as mock_status_mgr,
        ):
            mock_ctx.return_value.__enter__.return_value = cur
            loader._update_loader_status()

        marked_tables = [call.args[0] for call in mock_status_mgr.call_args_list]
        assert marked_tables == ["price_daily", *AUX_TABLES]

        mark_completed_calls = mock_status_mgr.return_value.mark_completed.call_args_list
        assert len(mark_completed_calls) == 1 + len(AUX_TABLES)

        # The primary (price_daily) call legitimately reports its own verified counts.
        primary_call = mark_completed_calls[0]
        assert primary_call.kwargs["current_run_symbols_loaded"] == 4886
        assert primary_call.kwargs["current_run_symbol_count"] == 4925

        # None of the 5 aux tables (a completely different, ~5-symbol ETF universe for 3 of
        # them) may be handed the stock run's counts - that's the exact corruption bug.
        for aux_call in mark_completed_calls[1:]:
            assert "current_run_symbols_loaded" not in aux_call.kwargs
            assert "current_run_symbol_count" not in aux_call.kwargs
