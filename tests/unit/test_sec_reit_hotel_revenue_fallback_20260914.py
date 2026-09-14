"""Regression test: hotel REITs use "RevenueFromLeasedAndOwnedHotels" as their real
revenue total, distinct from the equity-REIT concepts (RealEstateRevenueNet/
OperatingLeaseLeaseIncome) already wired - found during the 2026-09-14 goal session's
ratio-jump scan (a symbol's annual revenue jumping >20x between adjacent fiscal years).

CLDT (Chatham Lodging Trust, a real hotel REIT, SIC 6798) live-confirmed via real SEC
companyfacts JSON: FY2010 real "RevenueFromLeasedAndOwnedHotels"=$25,470,000 (confirmed
identically across two 10-Ks), growing to $276,950,000 by FY2015 - no "Revenues"/
"RealEstateRevenueNet"/"OperatingLeaseLeaseIncome" concept exists for this filer for
these years, so revenue fell back all the way to a genuinely unrelated, minor fact
(~$22K-$264K) - a ~1000x+ understatement across all 6 affected fiscal years, with no
data_unavailable/reason flag anywhere.

Wired via the same "reit_exclusive_fields" mechanism as real_estate_revenue_net/
operating_lease_lease_income - never touches "revenue" for a non-REIT filer at all,
regardless of processing order.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader


class TestReitHotelRevenueFallback:
    def _make_loader(self, reit_symbols: frozenset[str]) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_income_statement"
        loader.period = "annual"
        loader.statement_type = "income"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "revenue", "data_unavailable", "reason"})
        loader._field_mapping = {
            "revenue_from_leased_and_owned_hotels": "revenue",
            "interest_income_operating": "revenue",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset({"interest_income_operating"})
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_exclusive_fields = frozenset({"revenue_from_leased_and_owned_hotels"})
        loader._reit_symbols = reit_symbols
        return loader

    def test_cldt_real_revenue_recovered_from_hotel_reit_concept(self) -> None:
        loader = self._make_loader(reit_symbols=frozenset({"CLDT"}))
        row = {
            "symbol": "CLDT",
            "fiscal_year": 2010,
            "revenue_from_leased_and_owned_hotels": 25_470_000.0,
            "interest_income_operating": 193_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["revenue"] == 25_470_000.0

    def test_non_reit_symbol_never_gets_revenue_from_this_concept(self) -> None:
        loader = self._make_loader(reit_symbols=frozenset({"CLDT"}))
        row = {
            "symbol": "SOMECO",
            "fiscal_year": 2010,
            "revenue_from_leased_and_owned_hotels": 999_999_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0].get("revenue") is None
