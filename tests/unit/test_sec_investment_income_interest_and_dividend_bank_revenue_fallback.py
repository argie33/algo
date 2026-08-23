"""Regression test for the AROW-class community-bank revenue gap found live 2026-08-22
(goal session: real-money-readiness audit, following up on the "Insufficient history"
sample that found the IFRS-bank InterestRevenueExpense gap earlier the same day).

AROW (Arrow Financial Corp) live-confirmed via real companyfacts JSON: tags neither
"InterestAndDividendIncomeOperating" (the existing community-bank fallback) nor any
other revenue concept already mapped, for 13 straight years (2009-2021), despite real,
growing NetIncomeLoss on file every year (e.g. FY2015 $24,662,000). Its actual combined
interest+dividend income total is tagged under "InvestmentIncomeInterestAndDividend"
instead - live-verified FY2015 value ($70,738,000) exactly equals the sum of AROW's
itemized interest lines that year (InterestAndFeeIncomeLoansAndLeases $56,856,000 +
InterestIncomeSecuritiesTaxable $8,043,000 + InterestIncomeSecuritiesTaxExempt $5,745,000
+ InterestIncomeDomesticDeposits $94,000 = $70,738,000), confirming it's a real total,
not a partial line item. Mapping it (last in the revenue-concept list, fallback-only, so
it only wins when nothing else is present) recovers the real figure without risking a
clobber for any filer that reports a standard revenue concept.

Does NOT generalize to every small-bank revenue gap: live-checked BANR/CLBK/LSBK/PNFP
(same "Insufficient history" sample) have none of the concepts in this list at all, only
a filer-specific mix of itemized interest sub-line concepts with no single combined tag -
a structurally different, harder problem, deliberately not addressed by this fix.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader
from utils.external.sec_statements import get_income_statement


class TestInvestmentIncomeInterestAndDividendBankRevenueFallback:
    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_income_statement"
        loader.period = "annual"
        loader.statement_type = "income"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "revenue", "data_unavailable", "reason"})
        loader._field_mapping = {
            "revenues": "revenue",
            "interest_and_dividend_income_operating": "revenue",
            "investment_income_interest_and_dividend": "revenue",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset(
            {"interest_and_dividend_income_operating", "investment_income_interest_and_dividend"}
        )
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        return loader

    def test_concept_is_registered_in_income_statement_fetch_list(self) -> None:
        import inspect

        source = inspect.getsource(get_income_statement)
        assert '"InvestmentIncomeInterestAndDividend"' in source

    def test_investment_income_interest_and_dividend_populates_revenue_when_nothing_else_present(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "AROW",
            "fiscal_year": 2015,
            "investment_income_interest_and_dividend": 70_738_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["revenue"] == 70_738_000.0

    def test_investment_income_interest_and_dividend_does_not_overwrite_real_total_revenue(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "SOMEBANK",
            "fiscal_year": 2015,
            "revenues": 10_000_000_000.0,
            "investment_income_interest_and_dividend": 70_738_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["revenue"] == 10_000_000_000.0

    def test_interest_and_dividend_income_operating_still_wins_over_investment_income_variant(self) -> None:
        """Both are fallback-only, but interest_and_dividend_income_operating is listed
        first in _INCOME_FIELD_MAPPING - a filer reporting both (unseen so far, but the
        established defensive convention in this file) should keep the more commonly-used
        concept's value rather than the newer, narrower one."""
        loader = self._make_loader()
        row = {
            "symbol": "SOMEBANK2",
            "fiscal_year": 2015,
            "interest_and_dividend_income_operating": 50_000_000.0,
            "investment_income_interest_and_dividend": 70_738_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["revenue"] == 50_000_000.0
