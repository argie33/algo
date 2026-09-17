"""Regression test for the 2026-09-16 fix (goal: SEC-vs-yfinance divergence sweep,
our_value=0-vs-real-yfinance-value audit): BCSF (Bain Capital Specialty Finance, a BDC)
tags a real, correct tax provision under the investment-company-specific
"InvestmentIncomeOperatingTaxExpenseBenefit" concept ($4,475,000 FY2024, exactly matching
the yfinance-flagged value, live-confirmed via real SEC companyfacts JSON) AND a real $0
under the standard "IncomeTaxExpenseBenefit" concept for the same fiscal year.

The new concept alone was not enough: "IncomeTaxExpenseBenefit"=0 is processed first
(plain, non-fallback) and sets income_tax_expense=0, and the fallback-only guard's
`db_field in row` check then blocked the later, real $4,475,000 fallback value - same "an
already-stored exact 0 isn't necessarily a real total" ambiguity as long_term_debt/
capex/accounts_receivable, extended here to income_tax_expense via the
zero_blocking_real_value guard.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader
from loaders.load_financial_statements import _INCOME_FIELD_MAPPING, _REVENUE_FALLBACK_ONLY_FIELDS


class TestBcsfInvestmentIncomeTaxExpenseFixed:
    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_income_statement"
        loader.period = "annual"
        loader.statement_type = "income"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "income_tax_expense", "data_unavailable", "reason"})
        loader._field_mapping = {
            "income_tax_expense": "income_tax_expense",
            "income_tax_expense_benefit": "income_tax_expense",
            "investment_income_operating_tax_expense_benefit": "income_tax_expense",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset({"investment_income_operating_tax_expense_benefit"})
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        return loader

    def test_field_mapping_wires_new_concept_fallback_only(self) -> None:
        assert _INCOME_FIELD_MAPPING["investment_income_operating_tax_expense_benefit"] == "income_tax_expense"
        assert "investment_income_operating_tax_expense_benefit" in _REVENUE_FALLBACK_ONLY_FIELDS

    def test_zero_income_tax_expense_benefit_does_not_block_the_real_bdc_value(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "BCSF",
            "fiscal_year": 2024,
            "income_tax_expense_benefit": 0.0,
            "investment_income_operating_tax_expense_benefit": 4_475_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["income_tax_expense"] == 4_475_000.0
