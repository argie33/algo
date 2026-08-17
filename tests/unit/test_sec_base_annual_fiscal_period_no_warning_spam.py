"""Regression test for the 2026-08-17 fix to SecEdgarStatementLoader.transform() (loaders/
helpers/sec_base.py).

Annual SEC XBRL rows always carry a "fiscal_period" field (SEC tags it "FY"), but annual
statements intentionally have no field_mapping entry for it - annual tables have no
fiscal_quarter column, see _QUARTERLY_EXTRA's comment in load_financial_statements.py.
Before this fix, transform()'s generic "unmapped field" branch didn't know this was
expected, so it logged a WARNING for every single occurrence (i.e. every annual row of
every symbol) plus a per-symbol summary WARNING claiming the field was "being discarded"
as if it were a real data-mapping gap.

Live-confirmed 2026-08-17: one load_financial_statements run produced 40,050 of these
per-occurrence warnings plus 3,248 per-symbol summary warnings - 100% of them this single,
harmless, already-documented-as-expected field. That volume of pure noise buries any
genuinely actionable unmapped-field warning for other statement types.

Fixed: transform() now silently skips "fiscal_period" for annual statements instead of
logging it as unmapped. Quarterly statements are unaffected - fiscal_period is a real,
mapped field there (see test_sec_base_quarterly_unavailable_marker.py).
"""

import logging

from loaders.load_financial_statements import ConsolidatedFinancialStatementsLoader, get_income_statement_config


def _make_loader(period: str) -> ConsolidatedFinancialStatementsLoader:
    loader = ConsolidatedFinancialStatementsLoader.__new__(ConsolidatedFinancialStatementsLoader)
    config = get_income_statement_config(period)
    loader.table_name = config["table_name"]
    loader.period = period
    loader.statement_type = "income"
    loader._schema_cols = config["schema_cols"]
    loader._field_mapping = config["field_mapping"]
    return loader


class TestAnnualFiscalPeriodNoWarningSpam:
    def test_annual_fiscal_period_does_not_log_unmapped_warning(self, caplog) -> None:
        loader = _make_loader("annual")
        row = {"symbol": "AAPL", "fiscal_year": 2025, "fiscal_period": "FY", "revenues": 100}

        with caplog.at_level(logging.WARNING):
            transformed = loader.transform([row])

        assert len(transformed) == 1
        assert "fiscal_period" not in transformed[0]
        unmapped_warnings = [r for r in caplog.records if "Unmapped SEC field" in r.message]
        assert unmapped_warnings == [], "annual fiscal_period must not log an unmapped-field warning"
        summary_warnings = [r for r in caplog.records if "unmapped SEC XBRL concepts" in r.message]
        assert summary_warnings == [], "annual fiscal_period must not appear in the per-symbol summary either"

    def test_quarterly_fiscal_period_still_maps_to_fiscal_quarter(self) -> None:
        """Confirms the fix is annual-only - quarterly's real mapping is untouched."""
        loader = _make_loader("quarterly")
        row = {"symbol": "AAPL", "fiscal_year": 2025, "fiscal_period": "Q1", "revenues": 100}

        transformed = loader.transform([row])

        assert len(transformed) == 1
        assert transformed[0]["fiscal_quarter"] == 1

    def test_other_genuinely_unmapped_annual_fields_still_warn(self, caplog) -> None:
        """Guards against over-broadening the fix into a blanket unmapped-field suppression."""
        loader = _make_loader("annual")
        row = {"symbol": "AAPL", "fiscal_year": 2025, "some_new_untagged_concept": 42}

        with caplog.at_level(logging.WARNING):
            loader.transform([row])

        unmapped_warnings = [r for r in caplog.records if "Unmapped SEC field 'some_new_untagged_concept'" in r.message]
        assert len(unmapped_warnings) == 1
