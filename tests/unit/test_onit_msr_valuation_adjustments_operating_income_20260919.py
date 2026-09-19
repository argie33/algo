"""Regression tests for the 2026-09-19 ONIT (Onity Group, formerly Ocwen Financial) fix.

ONIT's real income statement has a separate "MSR valuation adjustments, net" line sitting
between "Total revenue" and "Total operating expenses" (tagged under the standard us-gaap
concept ServicingAssetAtFairValueChangesInFairValueResultingFromChangesInValuationInputs).
The generic revenue-minus-CostsAndExpenses fallback ignored it entirely, overstating
operating_income (FY2023: $654,600,000 vs a real $422,400,000).

Fixture values match the real filed FY2023 10-K (CIK 0000873860, accession
0001628280-24-007261, R5.htm), verified live 2026-09-19.
"""

from utils.external.sec_income_statement_fallbacks import (
    _fill_operating_income_from_revenue_minus_costs_and_expenses_and_msr_valuation,
)

_MSR_KEY = "servicing_asset_at_fair_value_changes_in_fair_value_resulting_from_changes_in_valuation_inputs"


class TestFillOperatingIncomeFromRevenueMinusCostsAndExpensesAndMsrValuation:
    def test_computes_operating_income_net_of_msr_valuation_adjustment(self) -> None:
        rows = [
            {
                "symbol": "ONIT",
                "fiscal_year": 2023,
                "revenues": 1_066_700_000.0,
                "costs_and_expenses": 412_100_000.0,
                _MSR_KEY: 232_200_000.0,
            }
        ]
        _fill_operating_income_from_revenue_minus_costs_and_expenses_and_msr_valuation(rows)
        assert rows[0]["operating_income_loss"] == 1_066_700_000.0 - 412_100_000.0 - 232_200_000.0
        assert "costs_and_expenses" not in rows[0]
        assert _MSR_KEY not in rows[0]

    def test_never_overwrites_a_real_operating_income_loss(self) -> None:
        rows = [
            {
                "symbol": "ONIT",
                "fiscal_year": 2023,
                "operating_income_loss": 100.0,
                "revenues": 1_000.0,
                "costs_and_expenses": 1.0,
                _MSR_KEY: 1.0,
            }
        ]
        _fill_operating_income_from_revenue_minus_costs_and_expenses_and_msr_valuation(rows)
        assert rows[0]["operating_income_loss"] == 100.0

    def test_does_not_fire_without_msr_concept_leaves_costs_and_expenses_for_sibling(self) -> None:
        rows = [{"symbol": "RRC", "fiscal_year": 2023, "revenues": 1_000.0, "costs_and_expenses": 500.0}]
        _fill_operating_income_from_revenue_minus_costs_and_expenses_and_msr_valuation(rows)
        assert "operating_income_loss" not in rows[0]
        assert rows[0]["costs_and_expenses"] == 500.0

    def test_does_not_fire_without_costs_and_expenses(self) -> None:
        rows = [{"symbol": "SOMEFILER", "fiscal_year": 2023, "revenues": 1_000.0, _MSR_KEY: 100.0}]
        _fill_operating_income_from_revenue_minus_costs_and_expenses_and_msr_valuation(rows)
        assert "operating_income_loss" not in rows[0]
