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


class TestInsuranceRevenueNotOverwrittenByAscContractRevenue:
    """FIXED 2026-08-22: same bug shape as the REIT case below, different industry trigger.
    Insurance contracts are explicitly out of ASC 606's scope (covered by ASC 944/IFRS 17
    instead), so an insurer's "RevenueFromContractWithCustomer*" tag - when present at all -
    is inherently a minor ancillary fee-revenue line, never the real premium/investment-
    income-driven total. Live-confirmed via MCY (Mercury General, P&C insurer, SIC 6331):
    real "Revenues" FY2025 = $5.99B, but RevenueFromContractWithCustomerIncludingAssessedTax
    FY2025 = $29.6M (a minor fee line) was clobbering it via the general (non-REIT-gated)
    priority chain."""

    def _make_loader(self, insurance_symbols: frozenset[str]) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_income_statement"
        loader.period = "annual"
        loader.statement_type = "income"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "revenue", "data_unavailable", "reason"})
        loader._field_mapping = {
            "revenues": "revenue",
            "revenue_from_contract_with_customer_including_assessed_tax": "revenue",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset()
        loader._reit_only_fallback_fields = frozenset({"revenue_from_contract_with_customer_including_assessed_tax"})
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = insurance_symbols
        return loader

    def test_insurer_real_revenue_not_overwritten_by_minor_asc606_fee_income(self) -> None:
        loader = self._make_loader(insurance_symbols=frozenset({"MCY"}))
        row = {
            "symbol": "MCY",
            "fiscal_year": 2025,
            "revenues": 5_992_468_000.0,
            "revenue_from_contract_with_customer_including_assessed_tax": 29_600_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["revenue"] == 5_992_468_000.0

    def test_non_insurer_still_uses_normal_priority_asc606_wins(self) -> None:
        loader = self._make_loader(insurance_symbols=frozenset({"MCY"}))
        row = {
            "symbol": "AAPL",
            "fiscal_year": 2025,
            "revenues": 300_000_000_000.0,
            "revenue_from_contract_with_customer_including_assessed_tax": 391_000_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["revenue"] == 391_000_000_000.0


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
        loader._insurance_symbols = frozenset()
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

    def test_reit_lease_revenue_wins_over_asc606_fee_income_regardless_of_dict_order(self):
        """FIXED 2026-08-22: live-confirmed via CPT (Camden Property Trust) - a REIT that
        reports NO "revenues" at all, only a small real ASC-606 fee-income figure AND the
        much larger correct lease-revenue figure under operating_lease_lease_income. Before
        this fix, whichever key happened to come first in the row dict's insertion order won
        - an implementation detail of _aggregate_concepts, not a real priority signal. Now
        operating_lease_lease_income always gets first claim on "revenue" for confirmed
        REITs, regardless of dict order."""
        loader = self._make_loader(reit_symbols=frozenset({"CPT"}))
        loader._field_mapping["operating_lease_lease_income"] = "revenue"
        loader._reit_exclusive_fields = frozenset({"operating_lease_lease_income"})
        row = {
            "symbol": "CPT",
            "fiscal_year": 2025,
            # ASC-606 fee income listed FIRST in the dict - the exact ordering that broke
            # this before the fix (dict insertion order mirrors sec_statements.py's
            # concepts list, where this concept sits before operating_lease_lease_income).
            "revenue_from_contract_with_customer_excluding_assessed_tax": 12_967_000.0,
            "operating_lease_lease_income": 1_573_544_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["revenue"] == 1_573_544_000.0

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
