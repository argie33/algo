"""Regression test for the 2026-09-16 fix (goal: SEC-vs-yfinance divergence sweep, second
follow-up pass): RAVE (Rave Restaurant Group, a franchisor) tags a real "CostOfRevenue"
fact at $0 (an unrelated, near-zero line item for this filer) alongside a real, much
larger "FranchisorCosts" fact ($3,956,000 FY2023, exactly matching the yfinance-flagged
value) for the same fiscal year. The plain "cost_of_revenue" concept's own real $0 was
permanently blocking the fallback-only "franchisor_costs" concept from ever writing, via
the same "stored 0 treated as already resolved" bug as every other field in
ZERO_FIRST_WRITE_GUARD_FIELDS.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader


class TestRaveFranchisorCostsZeroBlocking:
    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_income_statement"
        loader.period = "annual"
        loader.statement_type = "income"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "cost_of_revenue", "data_unavailable", "reason"})
        loader._field_mapping = {
            "cost_of_revenue": "cost_of_revenue",
            "franchisor_costs": "cost_of_revenue",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset({"franchisor_costs"})
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        return loader

    def test_real_nonzero_franchisor_costs_recovered_despite_earlier_plain_zero(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "RAVE",
            "fiscal_year": 2023,
            "cost_of_revenue": 0.0,
            "franchisor_costs": 3_956_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["cost_of_revenue"] == 3_956_000.0

    def test_genuine_zero_cost_of_revenue_still_preserved_when_no_fallback_value_exists(self) -> None:
        loader = self._make_loader()
        row = {"symbol": "NOCOGSCORP", "fiscal_year": 2025, "cost_of_revenue": 0.0}

        transformed = loader.transform([row])

        assert transformed[0]["cost_of_revenue"] == 0.0
