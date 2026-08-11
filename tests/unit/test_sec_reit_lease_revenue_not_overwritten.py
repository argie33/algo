"""Regression test for the REIT lease-revenue bug found live 2026-08-09 investigating UDR
(an equity REIT): its real revenue is reported under the legacy "Revenues" concept
($1.67B, mostly lease income - out of ASC 606's scope), but it also tags a small,
real non-lease fee-income line under the ASC-606 "contract with customer" concept
($8.3M). loaders/helpers/sec_base.py::transform()'s general priority chain treats the
ASC-606 tag as strictly superseding "Revenues" (true for most post-2018 filers, where
both tags describe the same total revenue at different points in the ASC-606
transition) - false for REITs specifically, where the two tags describe genuinely
different, non-overlapping revenue streams and the ASC-606 tag is only ever the minor
one.

Fixed via a REIT-only (SIC 6798) fallback: sec_base.py's transform() now only lets the
ASC-606 concepts overwrite "revenue" for REIT symbols when nothing else (the real
"revenues" figure) has already populated it.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader


class TestReitLeaseRevenueNotOverwrittenByAscContractRevenue:
    def _make_loader(self, reit_symbols: frozenset[str]):
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_income_statement"
        loader.period = "annual"
        loader.statement_type = "income"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "revenue", "data_unavailable", "reason"})
        loader._field_mapping = {
            "revenues": "revenue",
            "revenue_from_contract_with_customer_excluding_assessed_tax": "revenue",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset()
        loader._reit_only_fallback_fields = frozenset({"revenue_from_contract_with_customer_excluding_assessed_tax"})
        loader._reit_symbols = reit_symbols
        return loader

    def test_reit_real_lease_revenue_not_overwritten_by_minor_asc606_fee_income(self):
        loader = self._make_loader(reit_symbols=frozenset({"UDR"}))
        row = {
            "symbol": "UDR",
            "fiscal_year": 2025,
            "revenues": 1_670_000_000.0,
            "revenue_from_contract_with_customer_excluding_assessed_tax": 8_300_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["revenue"] == 1_670_000_000.0

    def test_reit_asc606_fee_income_still_wins_when_no_lease_revenue_present(self):
        loader = self._make_loader(reit_symbols=frozenset({"UDR"}))
        row = {
            "symbol": "UDR",
            "fiscal_year": 2025,
            "revenue_from_contract_with_customer_excluding_assessed_tax": 8_300_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["revenue"] == 8_300_000.0

    def test_non_reit_still_uses_normal_priority_asc606_wins(self):
        # Same shape of data, but the symbol isn't in the REIT set - a normal
        # post-2018 filer where the ASC-606 tag legitimately supersedes "revenues"
        # must be completely unaffected by this REIT-only carve-out.
        loader = self._make_loader(reit_symbols=frozenset({"UDR"}))
        row = {
            "symbol": "AAPL",
            "fiscal_year": 2025,
            "revenues": 300_000_000_000.0,
            "revenue_from_contract_with_customer_excluding_assessed_tax": 391_000_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["revenue"] == 391_000_000_000.0
