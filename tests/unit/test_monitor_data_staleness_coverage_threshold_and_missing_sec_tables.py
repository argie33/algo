"""Regression test for two gaps left after the base fix in 41c82cb76 (which stopped
check_all_tables()'s per-table "stale_threshold" KeyError for THRESHOLDS-driven tables):

1. The price_daily_symbol_coverage synthetic entry is built outside the THRESHOLDS loop and
   can independently reach level="critical" (insufficient symbol coverage), but had no
   "threshold_minutes" key at all - the same KeyError class, just a second call site.

2. annual_income_statement/company_info_sec are checked by Phase 1
   (algo/orchestrator/phase1_data_freshness.py, SESSION 116 FIX) as warn-only tables, but were
   entirely absent from this script's THRESHOLDS dict and get_table_age_minutes()'s
   timestamp_cols map - this operator-facing diagnostic tool was blind to two tables Phase 1
   actively gates on.
"""

from unittest.mock import patch

from scripts import monitor_data_staleness as mds


class TestSymbolCoverageEntryHasThreshold:
    def test_critical_coverage_shortfall_has_threshold_minutes_not_missing_key(self):
        with (
            patch.object(mds, "get_table_age_minutes", return_value=5.0),
            patch.object(mds, "get_loader_failed", return_value=False),
            patch.object(mds, "get_price_symbol_coverage", return_value=(10, 5000, 0.2)),
        ):
            results = mds.check_all_tables()

        entry = results["price_daily_symbol_coverage"]
        assert entry["level"] == "critical"
        assert "threshold_minutes" in entry
        assert entry["threshold_minutes"] is not None

    def test_healthy_coverage_also_has_threshold_minutes_key(self):
        with (
            patch.object(mds, "get_table_age_minutes", return_value=5.0),
            patch.object(mds, "get_loader_failed", return_value=False),
            patch.object(mds, "get_price_symbol_coverage", return_value=(10000, 10000, 100.0)),
        ):
            results = mds.check_all_tables()

        entry = results["price_daily_symbol_coverage"]
        assert entry["level"] == "ok"
        assert "threshold_minutes" in entry


class TestAnnualIncomeStatementAndCompanyInfoSecCovered:
    def test_both_tables_present_in_thresholds(self):
        assert "annual_income_statement" in mds.THRESHOLDS
        assert "company_info_sec" in mds.THRESHOLDS

    def test_both_tables_resolve_a_real_age_not_none(self):
        # Before this fix, these two were absent from get_table_age_minutes()'s
        # timestamp_cols map too, so even with a THRESHOLDS entry they'd always read
        # age=None ("[UNCONFIRMED] NO DATA") regardless of actual data freshness.
        with (
            patch.object(mds, "get_table_age_minutes", wraps=mds.get_table_age_minutes) as mock_age,
            patch.object(mds, "get_loader_failed", return_value=False),
        ):
            mock_age.side_effect = lambda table: (
                60.0 if table in ("annual_income_statement", "company_info_sec") else None
            )
            results = mds.check_all_tables()

        assert results["annual_income_statement"]["level"] == "ok"
        assert results["company_info_sec"]["level"] == "ok"


if __name__ == "__main__":
    import pytest

    pytest.main([__file__, "-v"])
