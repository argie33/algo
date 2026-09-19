"""Regression test for the 2026-09-19 fix (goal session: "confident in our data" sweep,
operating_income implausible-margin cluster investigation): insurers that tag a real
"BenefitsLossesAndExpenses" total (their COGS-equivalent, including the variable-annuity-
guarantee/hedging derivative losses and claims-incurred that dominate an insurer's costs) but
ALSO happen to tag a much narrower "CostsAndExpenses" fact for a different line item, or tag no
CostsAndExpenses at all.

Live-confirmed via real SEC companyfacts JSON:
- JXN (Jackson Financial, CIK 0001822993) FY2020: Revenue=$3,546,000,000,
  BenefitsLossesAndExpenses=$6,037,000,000 (restated), CostsAndExpenses=$1,299,000,000
  (restated, a much narrower concept). Before this fix,
  _fill_operating_income_from_revenue_minus_costs_and_expenses fired on the narrower concept
  first and produced operating_income=$2,247,000,000 for a year the filer actually posted a
  $2,491,000,000 pretax LOSS. Revenue - BenefitsLossesAndExpenses = -$2,491,000,000, an exact
  match to the filer's own tagged pretax_income.
- GNW (Genworth Financial, CIK 0001276520) FY2009: tags no CostsAndExpenses at all, only
  BenefitsLossesAndExpenses=$9,861,000,000. Revenue($9,069,000,000) -
  BenefitsLossesAndExpenses = -$792,000,000, exact match to pretax_income.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader
from loaders.load_financial_statements import _INCOME_FIELD_MAPPING
from utils.external.sec_statements import (
    _fill_operating_income_from_revenue_minus_benefits_losses_and_expenses,
    _fill_operating_income_from_revenue_minus_costs_and_expenses,
)


class TestJxnGnwOperatingIncomeFromBenefitsLossesAndExpenses:
    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_income_statement"
        loader.period = "annual"
        loader.statement_type = "income"
        loader._schema_cols = frozenset(
            {"symbol", "fiscal_year", "operating_income", "revenue", "data_unavailable", "reason"}
        )
        loader._field_mapping = dict(_INCOME_FIELD_MAPPING)
        loader._fallback_only_fields = frozenset()
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_exclusive_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        return loader

    def test_jxn_takes_priority_over_narrower_costs_and_expenses(self) -> None:
        rows = [
            {
                "symbol": "JXN",
                "fiscal_year": 2020,
                "revenues": 3_546_000_000.0,
                "benefits_losses_and_expenses": 6_037_000_000.0,
                "costs_and_expenses": 1_299_000_000.0,
            }
        ]

        _fill_operating_income_from_revenue_minus_benefits_losses_and_expenses(rows)
        assert rows[0]["operating_income_loss"] == -2_491_000_000.0

        # The narrower costs_and_expenses fallback must not overwrite it.
        _fill_operating_income_from_revenue_minus_costs_and_expenses(rows)
        assert rows[0]["operating_income_loss"] == -2_491_000_000.0

        transformed = self._make_loader().transform(rows)
        assert transformed[0]["operating_income"] == -2_491_000_000.0

    def test_gnw_style_no_costs_and_expenses_tagged_at_all(self) -> None:
        rows = [
            {
                "symbol": "GNW",
                "fiscal_year": 2009,
                "revenues": 9_069_000_000.0,
                "benefits_losses_and_expenses": 9_861_000_000.0,
            }
        ]

        _fill_operating_income_from_revenue_minus_benefits_losses_and_expenses(rows)
        assert rows[0]["operating_income_loss"] == -792_000_000.0

        transformed = self._make_loader().transform(rows)
        assert transformed[0]["operating_income"] == -792_000_000.0

    def test_never_overwrites_a_real_operating_income_value(self) -> None:
        rows = [
            {
                "symbol": "AAPL",
                "fiscal_year": 2025,
                "revenues": 400_000_000_000.0,
                "operating_income_loss": 120_000_000_000.0,
                "benefits_losses_and_expenses": 1.0,
            }
        ]

        _fill_operating_income_from_revenue_minus_benefits_losses_and_expenses(rows)

        assert rows[0]["operating_income_loss"] == 120_000_000_000.0

    def test_requires_some_revenue_concept(self) -> None:
        rows = [{"symbol": "XYZ", "fiscal_year": 2025, "benefits_losses_and_expenses": 1_000_000.0}]

        _fill_operating_income_from_revenue_minus_benefits_losses_and_expenses(rows)

        assert rows[0].get("operating_income_loss") is None

    def test_no_op_when_benefits_losses_and_expenses_absent(self) -> None:
        rows = [{"symbol": "XYZ", "fiscal_year": 2025, "revenues": 1_000_000.0}]

        _fill_operating_income_from_revenue_minus_benefits_losses_and_expenses(rows)

        assert rows[0].get("operating_income_loss") is None
