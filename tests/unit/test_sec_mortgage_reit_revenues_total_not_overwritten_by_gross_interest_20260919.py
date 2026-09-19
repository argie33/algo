"""Regression test for the ACR-class mortgage-REIT revenue bug found live 2026-09-19
(/goal data-confidence audit).

ACR (ACRES Commercial Realty Corp, CIK 0001332551) live-confirmed via real SEC companyfacts
JSON: its real, complete FY2023 revenue is tagged under "Revenues" ($91,131,000, exact
yfinance match) - a genuine NET total (interest income already net of interest expense on
ACR's own borrowings and other REIT operating costs), not a narrow fee-income sub-line.
ACR also separately tags "InterestAndDividendIncomeOperating" ($187,466,000, ~2x larger) -
its GROSS interest+dividend income before subtracting interest expense.

should_override_fallback_field_for_depository_institution (sec_reit_exclusive_scale_guard.py)
exists to let a bank/mortgage-REIT's real interest-income concept overwrite an already-
populated "revenue" when that existing value is a known-narrow sub-line (an ASC-606
contract-revenue fee concept, or a REIT-exclusive concept like operating_lease_lease_income -
see test_sec_bank_interest_income_revenue_not_overwritten.py's WAFDP case and
test_sec_reit_exclusive_field_overrides_residual_revenue_20260918.py's ABR/TRTX-shaped case).
Before this fix it was magnitude-gated ONLY ("genuinely larger wins"), which incorrectly
assumed any smaller existing "revenue" must be a narrow sub-line - wrong when the existing
value came from "Revenues"/"RevenuesNetOfInterestExpense" itself, since a real NET revenue
total is smaller than its own GROSS-interest component by definition. The fix denies the
override specifically when the existing value's source concept is one of those two genuine-
total concepts, while leaving every other documented case (AX/WAFDP-shaped ASC-606 sub-line,
ABR/TRTX-shaped REIT-exclusive sub-line) unaffected.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader


class TestMortgageReitRevenuesTotalNotOverwrittenByGrossInterest:
    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_income_statement"
        loader.period = "annual"
        loader.statement_type = "income"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "revenue", "data_unavailable", "reason"})
        loader._field_mapping = {
            "revenues": "revenue",
            "interest_and_dividend_income_operating": "revenue",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset({"interest_and_dividend_income_operating"})
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_exclusive_fields = frozenset()
        loader._reit_symbols = frozenset({"ACR"})
        loader._insurance_symbols = frozenset()
        loader._depository_institution_symbols = frozenset()
        return loader

    def test_acr_real_net_revenues_total_not_overwritten_by_gross_interest_income(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "ACR",
            "fiscal_year": 2023,
            "revenues": 91_131_000.0,
            "interest_and_dividend_income_operating": 187_466_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["revenue"] == 91_131_000.0

    def test_gross_interest_income_still_wins_when_no_revenues_total_present(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "ACR",
            "fiscal_year": 2020,
            "interest_and_dividend_income_operating": 100_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["revenue"] == 100_000_000.0
