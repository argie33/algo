"""Regression test: monitor_data_staleness.py must catch a per-symbol price_daily
coverage gap that its table-wide age check cannot see.

get_table_age_minutes() only measures MAX(updated_at) across the whole table - if 90%+ of
symbols got today's row, the table reads FRESH even while a batch-crash left a meaningful
chunk of individual symbols stuck for days. Phase 1 already fails-closed on this for
trading itself (algo/orchestrator/phase1_data_freshness.py), but the diagnostic tools
operators run before trading hours need per-symbol visibility for pre-trading validation.
Fixed by adding get_price_symbol_coverage(), mirroring Phase 1's own active-symbol-scoped
query, and cross-checking it against the same phase1_min_coverage_pct/phase1_min_symbol_count
config thresholds.

Also covers the 2026-09-01 fix: get_price_symbol_coverage() used to always check
`today - 1 day` regardless of time of day, so it could never see a same-day loader
failure that Phase 1 (which requires today's data once its 6 PM ET grace period ends)
would correctly halt on.
"""

from datetime import date, datetime
from unittest.mock import MagicMock, patch

from scripts import monitor_data_staleness as mds


class TestPriceSymbolCoverage:
    def test_get_price_symbol_coverage_computes_active_scoped_percentage(self):
        mock_cursor = MagicMock()
        mock_cursor.fetchone.side_effect = [(4700,), (5000,)]
        mock_db_ctx = MagicMock()
        mock_db_ctx.__enter__.return_value = mock_cursor

        with (
            patch.object(mds, "DatabaseContext", return_value=mock_db_ctx),
            patch.object(mds.MarketCalendar, "is_trading_day", return_value=True),
        ):
            result = mds.get_price_symbol_coverage()

        assert result == (4700, 5000, 94.0)

    def test_get_price_symbol_coverage_returns_none_on_db_error(self):
        with patch.object(mds, "DatabaseContext", side_effect=RuntimeError("db down")):
            assert mds.get_price_symbol_coverage() is None

    def test_get_price_symbol_coverage_requires_todays_date_after_6pm_on_a_trading_day(self):
        """After Phase 1's own 6 PM ET grace-period cutoff on a trading day, a same-day
        loader crash (today's coverage query returns 0) must be visible - not masked by
        checking yesterday's unrelated, complete coverage."""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.side_effect = [(0,), (5471,)]
        mock_db_ctx = MagicMock()
        mock_db_ctx.__enter__.return_value = mock_cursor

        with (
            patch.object(mds, "DatabaseContext", return_value=mock_db_ctx),
            patch.object(mds.MarketCalendar, "is_trading_day", return_value=True),
            patch.object(mds, "date") as mock_date,
            patch.object(mds, "datetime") as mock_datetime,
        ):
            mock_date.today.return_value = date(2026, 9, 1)
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
            mock_datetime.now.return_value = datetime(2026, 9, 1, 18, 30)  # 6:30 PM ET, trading day
            result = mds.get_price_symbol_coverage()

        assert result == (0, 5471, 0.0)
        query_date_arg = mock_cursor.execute.call_args_list[0].args[1][0]
        assert query_date_arg == date(2026, 9, 1)  # today, not yesterday

    def test_get_price_symbol_coverage_uses_prior_trading_day_before_6pm(self):
        """Before the 6 PM ET grace-period cutoff, today's close data isn't required yet -
        same behavior as before this fix."""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.side_effect = [(5471,), (5471,)]
        mock_db_ctx = MagicMock()
        mock_db_ctx.__enter__.return_value = mock_cursor

        with (
            patch.object(mds, "DatabaseContext", return_value=mock_db_ctx),
            patch.object(mds.MarketCalendar, "is_trading_day", return_value=True),
            patch.object(mds, "date") as mock_date,
            patch.object(mds, "datetime") as mock_datetime,
        ):
            mock_date.today.return_value = date(2026, 9, 1)
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
            mock_datetime.now.return_value = datetime(2026, 9, 1, 14, 0)  # 2 PM ET, before close
            mds.get_price_symbol_coverage()

        query_date_arg = mock_cursor.execute.call_args_list[0].args[1][0]
        assert query_date_arg == date(2026, 8, 31)  # yesterday, not today

    def test_get_price_symbol_coverage_falls_back_on_non_trading_day_even_after_6pm(self):
        """On a weekend/holiday, there's no "close" today to be after regardless of clock
        time - must still walk back to the most recent real trading day."""
        mock_cursor = MagicMock()
        mock_cursor.fetchone.side_effect = [(5471,), (5471,)]
        mock_db_ctx = MagicMock()
        mock_db_ctx.__enter__.return_value = mock_cursor

        with (
            patch.object(mds, "DatabaseContext", return_value=mock_db_ctx),
            patch.object(mds.MarketCalendar, "is_trading_day", side_effect=lambda d: d != date(2026, 9, 1)),
            patch.object(mds, "date") as mock_date,
            patch.object(mds, "datetime") as mock_datetime,
        ):
            mock_date.today.return_value = date(2026, 9, 1)
            mock_date.side_effect = lambda *a, **kw: date(*a, **kw)
            mock_datetime.now.return_value = datetime(2026, 9, 1, 20, 0)  # 8 PM ET, but not a trading day
            mds.get_price_symbol_coverage()

        query_date_arg = mock_cursor.execute.call_args_list[0].args[1][0]
        assert query_date_arg == date(2026, 8, 31)  # most recent real trading day

    def test_check_all_tables_flags_insufficient_symbol_coverage_as_critical(self):
        with (
            patch.object(mds, "get_table_age_minutes", return_value=60.0),
            patch.object(mds, "get_loader_failed", return_value=False),
            patch.object(mds, "get_price_symbol_coverage", return_value=(1, 5471, 0.02)),
        ):
            results = mds.check_all_tables()

        assert results["price_daily_symbol_coverage"]["level"] == "critical"
        assert "INSUFFICIENT" in results["price_daily_symbol_coverage"]["status"]

    def test_check_all_tables_reports_ok_when_coverage_is_sufficient(self):
        with (
            patch.object(mds, "get_table_age_minutes", return_value=60.0),
            patch.object(mds, "get_loader_failed", return_value=False),
            patch.object(mds, "get_price_symbol_coverage", return_value=(5200, 5471, 95.0)),
        ):
            results = mds.check_all_tables()

        assert results["price_daily_symbol_coverage"]["level"] == "ok"

    def test_check_all_tables_falls_back_to_defaults_if_config_unavailable(self):
        with (
            patch.object(mds, "get_table_age_minutes", return_value=60.0),
            patch.object(mds, "get_loader_failed", return_value=False),
            patch.object(mds, "get_price_symbol_coverage", return_value=(100, 5471, 1.8)),
            patch("algo.infrastructure.config.main.get_config", side_effect=RuntimeError("no config")),
        ):
            results = mds.check_all_tables()

        # 1.8% coverage must still fail even the hardcoded fallback thresholds (75%/5000).
        assert results["price_daily_symbol_coverage"]["level"] == "critical"


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
