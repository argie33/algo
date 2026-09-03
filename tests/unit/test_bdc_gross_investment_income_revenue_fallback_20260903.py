"""Regression test for the 2026-09-03 fix (goal session: "missing SEC/XBRL data under 6k"
sweep, no_recent_revenue_symbols investigation): BDCs (business development companies)
report neither any standard revenue concept nor any of the existing bank/REIT/utility
revenue-fallback concepts - their top-line revenue-equivalent is "GrossInvestmentIncome
Operating" (total investment income before fund operating expenses).

Live-confirmed via real SEC companyfacts JSON: CSWC (Capital Southwest) FY2026 (period
ended 2026-03-31) $232,105,000, PFLT (PennantPark Floating Rate Capital) FY2025
$261,427,000 - both real, current, zero-NULL-alternative figures. Deliberately NOT
"NetInvestmentIncome" (after fund operating expenses - CSWC FY2026 $136,588,000 vs. this
gross figure's $232,105,000, ~59% of gross).

Fallback-only so it never overwrites a real revenue figure a normal-priority concept
already found (most BDCs, e.g. MAIN, already have real revenue via another route).
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader
from loaders.load_financial_statements import _INCOME_FIELD_MAPPING, _REVENUE_FALLBACK_ONLY_FIELDS


class TestBdcGrossInvestmentIncomeRevenueFallback:
    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_income_statement"
        loader.period = "annual"
        loader.statement_type = "income"
        loader._schema_cols = frozenset(
            {"symbol", "fiscal_year", "revenue", "net_income", "data_unavailable", "reason"}
        )
        loader._field_mapping = {
            "revenues": "revenue",
            "gross_investment_income_operating": "revenue",
            "net_income_loss": "net_income",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset({"gross_investment_income_operating"})
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        return loader

    def test_field_mapping_wires_concept_to_revenue_as_fallback_only(self) -> None:
        assert _INCOME_FIELD_MAPPING["gross_investment_income_operating"] == "revenue"
        assert "gross_investment_income_operating" in _REVENUE_FALLBACK_ONLY_FIELDS

    def test_bdc_with_no_other_revenue_concept_recovered(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "CSWC",
            "fiscal_year": 2026,
            "gross_investment_income_operating": 232_105_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["revenue"] == 232_105_000.0

    def test_does_not_overwrite_real_revenue_from_standard_concept(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "MAIN",
            "fiscal_year": 2025,
            "revenues": 566_391_000.0,
            "gross_investment_income_operating": 400_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["revenue"] == 566_391_000.0
