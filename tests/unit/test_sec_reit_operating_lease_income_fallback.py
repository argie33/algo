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

Wired as a REIT-only (SIC 6798) fallback, same precedent as the existing ASC-606
contract-revenue REIT carve-out (test_sec_reit_lease_revenue_not_overwritten.py):
"revenues" (when present) is the fuller total including non-lease fee income, so this
concept should only fill "revenue" once "revenues" itself has gone empty.
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
        loader._reit_only_fallback_fields = frozenset({"operating_lease_lease_income"})
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

    def test_non_reit_symbol_unaffected_by_carve_out(self):
        loader = self._make_loader(reit_symbols=frozenset({"AMH"}))
        row = {
            "symbol": "SOMECO",
            "fiscal_year": 2025,
            "revenues": 500_000_000.0,
            "operating_lease_lease_income": 12_000_000.0,
        }

        transformed = loader.transform([row])

        # Non-REIT: normal priority applies - operating_lease_lease_income isn't REIT-gated
        # away since the symbol isn't in the REIT set, so plain "last listed wins" applies.
        # Here "operating_lease_lease_income" is iterated after "revenues" in the dict, so
        # it would win under plain last-wins semantics - this test documents that a non-REIT
        # symbol simply isn't protected by the carve-out (expected: this concept should
        # essentially never appear for a non-REIT filer in practice).
        assert transformed[0]["revenue"] == 12_000_000.0
