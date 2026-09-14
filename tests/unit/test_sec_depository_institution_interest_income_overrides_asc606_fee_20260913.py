"""Regression test: a bank/depository-institution's real interest-income revenue concept
must be able to override an ASC-606 fee-only concept found first (goal session 2026-09-13,
"patrols and checks" comprehensiveness audit, quarterly_revenue_sum_vs_annual_extreme
quarantine backlog follow-up).

AX (Axos Financial, SIC 6035, a savings institution): live-confirmed via real SEC
companyfacts JSON, FY2022 (fiscal year ends June 30) real revenue is
InterestAndDividendIncomeOperating=$659,728,000, but RevenueFromContractWithCustomer
ExcludingAssessedTax=$59,434,000 (real, but ASC 606 explicitly excludes interest income, so
this only captures a minor non-interest fee-income line) is processed FIRST in the concept
list (AX tags no "Revenues"/other higher-priority concept), winning "revenue" via the
ordinary non-fallback priority chain. InterestAndDividendIncomeOperating is plain
fallback-only, so it then just defers to the already-populated smaller value with no
magnitude check - understating annual revenue ~11x for 9 straight fiscal years
(2018-2026) with no data_unavailable/reason flag anywhere.

Same conceptual bug as the already-fixed REIT/insurance/depository case
(should_skip_reit_only_fallback_field, UDR/WAFDP), but the REVERSE processing order: that
guard protects a real total found FIRST from an ASC-606 concept found LATER. This fix
handles a bank's real interest-income concept found LATER needing to correct an ASC-606
concept found FIRST.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader


class TestDepositoryInstitutionInterestIncomeOverridesAsc606Fee:
    def _make_loader(self, depository_symbols=frozenset({"AX"})):
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_income_statement"
        loader.period = "annual"
        loader.statement_type = "income"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "revenue", "data_unavailable", "reason"})
        loader._field_mapping = {
            "revenue_from_contract_with_customer_excluding_assessed_tax": "revenue",
            "interest_and_dividend_income_operating": "revenue",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset({"interest_and_dividend_income_operating"})
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_exclusive_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        loader._depository_institution_symbols = depository_symbols
        return loader

    def test_ax_2022_real_interest_income_wins_over_small_asc606_fee_concept(self):
        loader = self._make_loader()
        row = {
            "symbol": "AX",
            "fiscal_year": 2022,
            "revenue_from_contract_with_customer_excluding_assessed_tax": 59_434_000.0,
            "interest_and_dividend_income_operating": 659_728_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["revenue"] == 659_728_000.0

    def test_non_depository_symbol_unaffected_asc606_fee_concept_still_wins(self):
        """A non-bank filer with a small interest-income side-line must NOT have its real
        ASC-606 revenue overwritten by that unrelated fact - same KARO-shaped protection as
        the existing magnitude-resolved group tests."""
        loader = self._make_loader(depository_symbols=frozenset())
        row = {
            "symbol": "ORLY",
            "fiscal_year": 2022,
            "revenue_from_contract_with_customer_excluding_assessed_tax": 4_000_000_000.0,
            "interest_and_dividend_income_operating": 1_750_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["revenue"] == 4_000_000_000.0

    def test_depository_institution_larger_asc606_revenue_not_shrunk(self):
        """Magnitude-gated: a bank whose ASC-606 fee revenue genuinely exceeds its interest
        income must keep the larger, correct ASC-606 figure."""
        loader = self._make_loader()
        row = {
            "symbol": "AX",
            "fiscal_year": 2022,
            "revenue_from_contract_with_customer_excluding_assessed_tax": 700_000_000.0,
            "interest_and_dividend_income_operating": 659_728_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["revenue"] == 700_000_000.0
