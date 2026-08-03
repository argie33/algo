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
"""

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
