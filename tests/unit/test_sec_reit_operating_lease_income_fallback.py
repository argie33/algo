"""Regression test: equity REITs (AMH/American Homes 4 Rent, EQR/Equity Residential
live-confirmed via real SEC companyfacts JSON) adopted "OperatingLeaseLeaseIncome" (ASC
842, the 2019 lease-accounting standard) as their real top-line lease-revenue tag -
"Revenues" goes silent for these filers right around the same transition (AMH's last real
"Revenues" entry is FY2020: $1.1828B) while OperatingLeaseLeaseIncome continues with real,
growing figures for years after (AMH FY2025=$1.850B, EQR FY2025=$3.094B).

Before this fix, `annual_income_statement.revenue` was NULL for AMH/EQR's 5-6 most recent
fiscal years despite the company continuing to file real, current 10-Ks every year -
same "revenue concept silently re-tagged, freezing the whole downstream quality/growth
metrics row behind a stale anchor" bug class as the AEG/UBS/XEL/DTE/OGS fixes, a
lease-accounting-standard trigger this time.

Wired via sec_base.py's "reit_exclusive_fields" (not the "reit_only_fallback_fields" used
by the ASC-606 contract-revenue REIT carve-out in test_sec_reit_lease_revenue_not_
overwritten.py): "revenues" (when present) is the fuller total including non-lease fee
income, so this concept should only fill "revenue" once "revenues" itself has gone empty -
AND, unlike the ASC-606 concepts, must never touch "revenue" for a non-REIT filer at all
(see the 2026-08-19 bug-found comment on the non-REIT test below for why a plain
fallback-only gate isn't strict enough for this specific concept).
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader


class TestReitOperatingLeaseIncomeFallback:
    def _make_loader(self, reit_symbols: frozenset[str]):
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_income_statement"
        loader.period = "annual"
        loader.statement_type = "income"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "revenue", "data_unavailable", "reason"})
        loader._field_mapping = {
            "revenues": "revenue",
            "operating_lease_lease_income": "revenue",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset()
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_exclusive_fields = frozenset({"operating_lease_lease_income"})
        loader._reit_symbols = reit_symbols
        return loader

    def test_real_total_revenue_not_overwritten_by_lease_income_when_both_present(self):
        # AMH's FY2020 overlap year: "revenues" ($1.1828B) is the fuller total; the lease
        # figure ($1.1725B) alone must not silently replace it.
        loader = self._make_loader(reit_symbols=frozenset({"AMH"}))
        row = {
            "symbol": "AMH",
            "fiscal_year": 2020,
            "revenues": 1_182_836_000.0,
            "operating_lease_lease_income": 1_172_514_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["revenue"] == 1_182_836_000.0

    def test_lease_income_recovers_revenue_once_revenues_tag_goes_silent(self):
        # AMH's FY2025: "Revenues" no longer tagged at all, only the lease concept.
        loader = self._make_loader(reit_symbols=frozenset({"AMH"}))
        row = {
            "symbol": "AMH",
            "fiscal_year": 2025,
            "operating_lease_lease_income": 1_850_234_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["revenue"] == 1_850_234_000.0

    def test_non_reit_symbol_real_revenue_not_overwritten_by_lease_income(self):
        # BUG FOUND 2026-08-19 (goal: "no SEC data"/loader audit): the REIT-only gate used
        # to only protect REIT filers from being overwritten - for any non-REIT symbol the
        # `symbol in reit_symbols` clause was False, so the guard fell through and wrote
        # unconditionally, exactly backwards from "REIT-only fallback". Live-confirmed via
        # IHRT (iHeartMedia, SIC 7812, not a REIT): its real annual "Revenues"
        # ($3.75B/$3.85B/$3.86B for FY2023-2025) was silently clobbered by its tiny real-
        # estate sublease income under this same concept ($2.01M/$787K/$562K - a ~1000x
        # understatement), because iHeartMedia also happens to report minor sublease income
        # under OperatingLeaseLeaseIncome - not the rare case the old test comment assumed.
        # A REIT-only fallback concept must never touch "revenue" for a non-REIT filer at
        # all, regardless of processing order.
        loader = self._make_loader(reit_symbols=frozenset({"AMH"}))
        row = {
            "symbol": "SOMECO",
            "fiscal_year": 2025,
            "revenues": 500_000_000.0,
            "operating_lease_lease_income": 12_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["revenue"] == 500_000_000.0
