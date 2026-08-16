"""Regression test for the 2026-08-16 fix: PriceLoader.run()'s non-trading-day skip branch
returned early without ever calling _finalize_execution_metrics() (the only place that marks
data_loader_status COMPLETED/FAILED for this loader - it doesn't go through runner.py's
generic argparse main()). Live-confirmed: price_daily and its 5 auxiliary tables were left
frozen at whatever status a prior (crashed) run last wrote - e.g. stuck at RUNNING/0%
completion all weekend - silently lying to the dashboard/Phase 1 about loader health even
though skipping on a non-trading day is correct, expected behavior.

Fixed to mark the primary table (and, for the stock loader, its 5 aux tables) COMPLETED via
the same "1/1 = no-op success" convention runner.py's global_mode path already uses for this
exact scenario, instead of leaving the status row untouched.
"""

from datetime import date
from unittest.mock import MagicMock, patch

from loaders.load_prices import PriceLoader


def _make_loader(table_name):
    loader = PriceLoader.__new__(PriceLoader)
    loader.table_name = table_name
    loader._backfill_days = 0
    return loader


class TestNonTradingDaySkipMarksStatus:
    @patch("loaders.load_prices.LoaderStatusManager")
    @patch("algo.infrastructure.MarketCalendar")
    def test_stock_skip_marks_primary_and_aux_tables_completed(self, mock_calendar, mock_status_mgr):
        mock_calendar.is_trading_day.return_value = False
        loader = _make_loader("price_daily")
        loader._validate_schema_preflight = MagicMock()

        with patch.dict("os.environ", {"ORCHESTRATOR_RUN_DATE": "2026-08-16"}):
            result = loader.run(["AAPL"], parallelism=1)

        assert result["status"] == "SKIPPED_NON_TRADING_DAY"

        marked_tables = [call.args[0] for call in mock_status_mgr.call_args_list]
        assert marked_tables == [
            "price_daily",
            "price_weekly",
            "price_monthly",
            "etf_price_daily",
            "etf_price_weekly",
            "etf_price_monthly",
        ]
        for instance_call in mock_status_mgr.return_value.mark_completed.call_args_list:
            assert instance_call.kwargs["current_run_symbols_loaded"] == 1
            assert instance_call.kwargs["current_run_symbol_count"] == 1

    @patch("loaders.load_prices.LoaderStatusManager")
    @patch("algo.infrastructure.MarketCalendar")
    def test_etf_skip_marks_only_its_own_table(self, mock_calendar, mock_status_mgr):
        mock_calendar.is_trading_day.return_value = False
        loader = _make_loader("etf_price_daily")
        loader._validate_schema_preflight = MagicMock()

        with patch.dict("os.environ", {"ORCHESTRATOR_RUN_DATE": "2026-08-16"}):
            loader.run(["SPY"], parallelism=1)

        marked_tables = [call.args[0] for call in mock_status_mgr.call_args_list]
        assert marked_tables == ["etf_price_daily"]

    @patch("loaders.load_prices.LoaderStatusManager")
    @patch("algo.infrastructure.MarketCalendar")
    def test_status_marking_failure_does_not_crash_the_skip(self, mock_calendar, mock_status_mgr):
        """A failure to mark status is logged, not fatal - the skip itself must still succeed."""
        mock_calendar.is_trading_day.return_value = False
        mock_status_mgr.return_value.mark_completed.side_effect = RuntimeError("db down")
        loader = _make_loader("price_daily")
        loader._validate_schema_preflight = MagicMock()

        with patch.dict("os.environ", {"ORCHESTRATOR_RUN_DATE": "2026-08-16"}):
            result = loader.run(["AAPL"], parallelism=1)

        assert result["status"] == "SKIPPED_NON_TRADING_DAY"

    @patch("loaders.load_prices.LoaderStatusManager")
    @patch("algo.infrastructure.MarketCalendar")
    def test_trading_day_does_not_take_the_skip_path(self, mock_calendar, mock_status_mgr):
        mock_calendar.is_trading_day.return_value = True
        loader = _make_loader("price_daily")
        loader._validate_schema_preflight = MagicMock()

        with patch.dict("os.environ", {"ORCHESTRATOR_RUN_DATE": "2026-08-13"}):
            try:
                loader.run(["AAPL"], parallelism=1)
            except Exception:
                pass

        assert mock_status_mgr.call_count == 0
