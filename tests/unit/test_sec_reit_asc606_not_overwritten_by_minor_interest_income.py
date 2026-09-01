"""Regression test for a REIT-side variant of the bank/thrift revenue-collision bug
(test_sec_bank_interest_income_revenue_not_overwritten.py), found during the 2026-08-31
goal session ("get all the data we need" full-coverage audit) while investigating a DB-wide
"cost_of_revenue >> revenue" scan.

CLDT (Chatham Lodging Trust, a real hotel REIT, SIC 7011) live-confirmed via real SEC
companyconcept JSON: reports NO "Revenues"/lease-income concept at all (hotel revenue isn't
tenant lease income, unlike office/apartment REITs), only a real ASC-606 total under
"RevenueFromContractWithCustomerIncludingAssessedTax" ($295,871,000 for FY2016) and an
unrelated, tiny "InvestmentIncomeInterestAndDividend" fact ($51,000, interest on cash).
Because that interest-income concept is generically fallback-only (not REIT-gated) it kept
its earlier position in `r`'s insertion order and claimed "revenue" first with the $51,000
figure - by the time the REIT-only-fallback ASC-606 concept was reached, its own
"skip if already populated, for a confirmed REIT" check saw "revenue" already set and
skipped, permanently blocking the real, much larger total. Same failure shape as the
already-fixed CPT case (test_sec_reit_lease_revenue_not_overwritten.py), just triggered by
a different pair of concepts.

Fixed by adding a magnitude check to that REIT/insurance/depository skip condition: only
protect the already-populated value if it ISN'T already smaller than the ASC-606 candidate.
This must not regress the WAFDP/AMTB bank case the skip was designed to protect (there the
existing value - real interest income - is already larger than the ASC-606 fee line, so the
magnitude check still protects it exactly as before).
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader


class TestReitAsc606NotOverwrittenByMinorInterestIncome:
    def _make_loader(self, reit_symbols: frozenset[str]) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_income_statement"
        loader.period = "annual"
        loader.statement_type = "income"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "revenue", "data_unavailable", "reason"})
        loader._field_mapping = {
            "revenue_from_contract_with_customer_including_assessed_tax": "revenue",
            "investment_income_interest_and_dividend": "revenue",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset({"investment_income_interest_and_dividend"})
        loader._reit_only_fallback_fields = frozenset({"revenue_from_contract_with_customer_including_assessed_tax"})
        loader._reit_symbols = reit_symbols
        loader._insurance_symbols = frozenset()
        loader._depository_institution_symbols = frozenset()
        return loader

    def test_reit_real_asc606_total_not_overwritten_by_minor_interest_income(self) -> None:
        loader = self._make_loader(reit_symbols=frozenset({"CLDT"}))
        row = {
            "symbol": "CLDT",
            "fiscal_year": 2016,
            "revenue_from_contract_with_customer_including_assessed_tax": 295_871_000.0,
            "investment_income_interest_and_dividend": 51_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["revenue"] == 295_871_000.0

    def test_bank_case_still_protected_existing_larger_interest_income_not_overwritten(self) -> None:
        """Guard against over-fixing: the WAFDP bank case needs the OPPOSITE outcome - a
        real, larger interest-income total must still beat a smaller ASC-606 fee line."""
        loader = self._make_loader(reit_symbols=frozenset())
        loader._depository_institution_symbols = frozenset({"WAFDP"})
        loader._field_mapping["interest_and_dividend_income_operating"] = "revenue"
        loader._fallback_only_fields = frozenset({"interest_and_dividend_income_operating"})
        loader._reit_only_fallback_fields = frozenset({"revenue_from_contract_with_customer_including_assessed_tax"})
        row = {
            "symbol": "WAFDP",
            "fiscal_year": 2018,
            "revenue_from_contract_with_customer_including_assessed_tax": 25_904_000.0,
            "interest_and_dividend_income_operating": 607_083_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["revenue"] == 607_083_000.0
