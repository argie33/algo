"""Regression test for the BENF (Beneficient) revenue-substitution bug (2026-09-14,
quarantine-backlog continuation) - the sec_base.py half of the fix (see
tests/unit/test_sec_revenue_total_negative_rejected_marker_20260914.py for the
sec_revenue_total_resolution.py half).

Live-confirmed via BENF's real SEC companyfacts JSON: BENF is a trust-structure filer whose
real annual "Revenues" legitimately goes negative from fair-value losses (-$98.696M for
FY2024). Before this fix, resolve_revenue_total_candidate silently rejected that negative
value without ever writing `row["revenue"]`, so sec_base.py's fallback-only single-line
concepts (InterestIncomeOperating/InterestAndDividendIncomeOperating) saw "revenue" as
genuinely missing and substituted their own much-smaller positive interest-income sub-line
($457,000) as if it were the total - understating a real ~$99M loss as if BENF had almost no
revenue at all.

Fixed by having a rejected negative candidate record a "negative_total_rejected" marker that
sec_base.py's fallback-only check now also treats as "already resolved", the same way it
already treats `db_field in row`.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader


class TestNegativeRevenueBlocksInterestIncomeFallback:
    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_income_statement"
        loader.period = "annual"
        loader.statement_type = "income"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "revenue", "data_unavailable", "reason"})
        loader._field_mapping = {
            "revenues": "revenue",
            "interest_income_operating": "revenue",
            "interest_and_dividend_income_operating": "revenue",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset(
            {"interest_income_operating", "interest_and_dividend_income_operating"}
        )
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        loader._depository_institution_symbols = frozenset()
        return loader

    def test_negative_real_total_leaves_revenue_unset_not_substituted(self) -> None:
        """The real BENF shape: a genuine, real, negative annual "Revenues" fact must not be
        replaced by a much-smaller-but-positive interest-income sub-line - revenue should stay
        unset (missing, honestly) rather than silently wrong."""
        loader = self._make_loader()
        row = {
            "symbol": "BENF",
            "fiscal_year": 2024,
            "revenues": -98_696_000.0,
            "interest_income_operating": 457_000.0,
        }

        transformed = loader.transform([row])

        assert "revenue" not in transformed[0] or transformed[0].get("revenue") is None

    def test_interest_income_still_wins_when_no_negative_total_present(self) -> None:
        """Mortgage REITs (AGNC, NLY) with no "revenues" concept at all must still get
        InterestIncomeOperating as their revenue - this fix must not regress that path."""
        loader = self._make_loader()
        row = {
            "symbol": "AGNC",
            "fiscal_year": 2023,
            "interest_income_operating": 1_500_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["revenue"] == 1_500_000_000.0

    def test_positive_real_total_still_wins_normally(self) -> None:
        """A genuine positive "revenues" fact must still populate revenue and block the
        interest-income fallback, same as before this fix."""
        loader = self._make_loader()
        row = {
            "symbol": "SOMECO",
            "fiscal_year": 2023,
            "revenues": 5_000_000.0,
            "interest_income_operating": 100_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["revenue"] == 5_000_000.0
