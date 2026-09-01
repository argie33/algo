"""Regression test: older-era (pre-ASC 842, largely pre-2016) equity REITs used
"RealEstateRevenueNet" as their real estate rental revenue total before
"OperatingLeaseLeaseIncome" existed as a tag at all - this concept was never fetched at
all before this fix, found during the 2026-08-31 goal session ("get all the data we need"
full-coverage audit) while investigating a DB-wide "cost_of_revenue >> revenue" scan.

ARE (Alexandria Real Estate Equities, a real office/lab REIT, SIC 6798) live-confirmed via
real SEC companyconcept JSON: FY2010 real "RealEstateRevenueNet"=$460,621,000 (restated
figure; originally filed $487,303,000, both plausible for ARE's real historical scale) - no
"Revenues"/"OperatingLeaseLeaseIncome"/ASC-606 concept exists for this filer at all for
that era, so revenue fell back all the way to a genuinely unrelated, minor
"InterestIncomeOperating" fact ($800,000) - a ~575x understatement with no
data_unavailable/reason flag anywhere.

Wired via the same "reit_exclusive_fields" mechanism as operating_lease_lease_income
(test_sec_reit_operating_lease_income_fallback.py) - never touches "revenue" for a
non-REIT filer at all, regardless of processing order.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader


class TestReitRealEstateRevenueNetFallback:
    def _make_loader(self, reit_symbols: frozenset[str]) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_income_statement"
        loader.period = "annual"
        loader.statement_type = "income"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "revenue", "data_unavailable", "reason"})
        loader._field_mapping = {
            "real_estate_revenue_net": "revenue",
            "interest_income_operating": "revenue",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset({"interest_income_operating"})
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_exclusive_fields = frozenset({"real_estate_revenue_net"})
        loader._reit_symbols = reit_symbols
        return loader

    def test_are_real_revenue_recovered_from_legacy_reit_concept(self) -> None:
        loader = self._make_loader(reit_symbols=frozenset({"ARE"}))
        row = {
            "symbol": "ARE",
            "fiscal_year": 2010,
            "real_estate_revenue_net": 460_621_000.0,
            "interest_income_operating": 800_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["revenue"] == 460_621_000.0

    def test_non_reit_symbol_never_gets_revenue_from_this_concept(self) -> None:
        loader = self._make_loader(reit_symbols=frozenset({"ARE"}))
        row = {
            "symbol": "SOMECO",
            "fiscal_year": 2010,
            "real_estate_revenue_net": 999_999_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0].get("revenue") is None
