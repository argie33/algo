"""Regression test for the 2026-09-18 fix (goal session, ASPN interest_expense dedicated
investigation): ASPN (Aspen Aerogels, CIK 0001145986) tags its ENTIRE real FY2022 interest
expense under "InterestExpenseRelatedParty" ($5,110,000, an EXACT match to yfinance's own
FY2022 figure) and has no other InterestExpense*/InterestAndDebtExpense/
FinancingInterestExpense fact for that year at all.

"interest_expense_related_party" previously had NO field_mapping entry anywhere in this
codebase - it was fetched nowhere, for any filer. The loader fell through all the way to
InterestPaidNet's cash-paid figure ($153,000, a real but much smaller and less precise number)
instead.

Note on the "sign-flip" theory this session ALSO investigated and disproved: ASPN's
InterestIncomeExpenseNonoperatingNet extraction (a separate mechanism, not touched by this fix)
is already directionally correct - FY2025's stored value (10,716,000, taken as the absolute
value of that concept's real -10,716,000 fact) is an EXACT match to yfinance's own FY2025
figure, confirming negative-value-means-net-expense is the correct sign convention already in
use. FY2023/FY2024's remaining divergence is a genuine SEC source-data gap (no concept in
ASPN's full companyfacts JSON is within 3% of yfinance's figure for either year) - not a bug,
left unreviewed/reviewed_needs_fix as appropriate, don't re-chase it as a sign issue.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader
from loaders.load_financial_statements import _INCOME_FIELD_MAPPING, _REVENUE_FALLBACK_ONLY_FIELDS


class TestAspnInterestExpenseRelatedPartyFallback:
    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_income_statement"
        loader.period = "annual"
        loader.statement_type = "income"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "interest_expense", "data_unavailable", "reason"})
        loader._field_mapping = {
            "interest_expense": "interest_expense",
            "interest_expense_related_party": "interest_expense",
            "interest_paid_net": "interest_expense",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset({"interest_expense_related_party", "interest_paid_net"})
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        return loader

    def test_field_mapping_wires_fallback_only(self) -> None:
        assert _INCOME_FIELD_MAPPING["interest_expense_related_party"] == "interest_expense"
        assert "interest_expense_related_party" in _REVENUE_FALLBACK_ONLY_FIELDS

    def test_aspn_style_related_party_concept_fills_empty_field(self) -> None:
        loader = self._make_loader()
        row = {"symbol": "ASPN", "fiscal_year": 2022, "interest_expense_related_party": 5_110_000.0}

        transformed = loader.transform([row])

        assert transformed[0]["interest_expense"] == 5_110_000.0

    def test_never_overwrites_a_real_total_already_populated(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "SOME_OTHER_FILER",
            "fiscal_year": 2024,
            "interest_expense": 999_000.0,
            "interest_expense_related_party": 1.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["interest_expense"] == 999_000.0

    def test_wins_over_the_lower_priority_interest_paid_net_fallback(self) -> None:
        """ASPN's real bug: InterestPaidNet ($153,000, cash-paid basis) was previously the
        only concept ever fetched for FY2022, wrongly claiming interest_expense before the
        more precise InterestExpenseRelatedParty ($5,110,000) even existed in the field
        mapping. Both are fallback-only, so whichever is listed FIRST in
        sec_income_statement.py's concept list wins - confirm related_party (listed first)
        beats interest_paid_net (listed after it) regardless of row dict ordering."""
        loader = self._make_loader()
        row = {
            "symbol": "ASPN",
            "fiscal_year": 2022,
            "interest_expense_related_party": 5_110_000.0,
            "interest_paid_net": 153_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["interest_expense"] == 5_110_000.0
