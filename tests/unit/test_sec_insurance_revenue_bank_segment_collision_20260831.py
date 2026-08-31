"""Regression test for the InsuranceRevenue/bank-total-revenue collision found live
2026-08-31 (goal session: "get all the data we need" full-coverage audit).

BBVA and HSBC both live-confirmed via real SEC companyfacts JSON to report a real
"InsuranceRevenue" fact from their minority insurance subsidiaries (BBVA's is even
NEGATIVE - EUR -3.627B FY2025, the segment's net result, not a revenue total) sharing
the EXACT SAME filed date as their own real consolidated total (BBVA's ~EUR26.28B
tagged InterestRevenueExpense; HSBC's ~$68.27B tagged RevenueAndOperatingIncome).
_aggregate_concepts's tiebreak in sec_statements.py keeps whichever fact was inserted
first on an exact filed-date tie, and InsuranceRevenue happened to be listed earlier in
_INCOME_IFRS_ALIASES than either - so BBVA's stored revenue was a small negative number
and HSBC's was ~20x too small, both silently (no data_unavailable/reason flag), for 4+
fiscal years each. AEG (a genuine insurer with no bank-interest concepts) must keep using
InsuranceRevenue as its real total unaffected by this fix.
"""

from decimal import Decimal

from loaders.helpers.sec_base import SecEdgarStatementLoader


class TestInsuranceRevenueBankSegmentCollision:
    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_income_statement"
        loader.period = "annual"
        loader.statement_type = "income"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "revenue", "data_unavailable", "reason"})
        loader._field_mapping = {
            "revenues": "revenue",
            "insurance_revenue": "revenue",
            "revenues_net_of_interest_expense": "revenue",
            "interest_revenue_expense": "revenue",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset({"interest_revenue_expense"})
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        return loader

    def test_bbva_negative_insurance_segment_loses_to_real_bank_total(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "BBVA",
            "fiscal_year": 2025,
            "insurance_revenue": -4_261_744_177.85,
            "interest_revenue_expense": 26_280_000_000.0 / 1.075,  # illustrative USD-converted scale
        }

        transformed = loader.transform([row])

        assert transformed[0]["revenue"] > 0
        assert transformed[0]["revenue"] == row["interest_revenue_expense"]

    def test_hsbc_small_insurance_segment_loses_to_larger_real_total(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "HSBC",
            "fiscal_year": 2025,
            "insurance_revenue": 3_228_000_000.0,
            "revenues": 68_274_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["revenue"] == 68_274_000_000.0

    def test_pure_insurer_still_uses_insurance_revenue_when_nothing_bigger_present(self) -> None:
        """AEG-shaped case: no bank-interest concept present at all, InsuranceRevenue is
        the only candidate and must still win."""
        loader = self._make_loader()
        row = {
            "symbol": "AEG",
            "fiscal_year": 2025,
            "insurance_revenue": 9_097_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["revenue"] == 9_097_000_000.0

    def test_decimal_values_from_db_still_compare_correctly(self) -> None:
        """annual_income_statement values round-trip as Decimal, not float - the
        magnitude comparison must not crash or misbehave on Decimal input."""
        loader = self._make_loader()
        row = {
            "symbol": "BBVA",
            "fiscal_year": 2024,
            "insurance_revenue": Decimal("-3629903590.43"),
            "interest_revenue_expense": Decimal("23517000000.00"),
        }

        transformed = loader.transform([row])

        assert transformed[0]["revenue"] == Decimal("23517000000.00")
