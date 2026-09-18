"""Regression test for a 2026-09-18 fix (goal session: quarantine-backlog continuation) to
loaders/helpers/sec_base.py's transform() - the `_reit_exclusive_fields` branch's
fallback-only rule ("never overwrite `revenue` once populated") assumed whatever concept
populated `revenue` first for a confirmed REIT was always at least as authoritative as a
REIT-exclusive concept arriving later. That's backwards when the earlier concept's own value
is a residual/near-zero fee line, not the REIT's real revenue total.

Live-confirmed via NYC (New York City REIT, CIK 0001595527, SIC 6798): its own FY2024 10-K
tags "Revenues" (processed first, in the magnitude-resolved candidate group) at
$800,000/$700,000/$0 for FY2022/2023/2024, while OperatingLeaseLeaseIncome (REIT-exclusive,
processed later) reports the real, much larger, quarter-consistent lease-revenue total for
the SAME 3 years ($64,005,000/$62,710,000/$61,570,000, exactly matching the sum of NYC's own
real discrete quarterly Revenues facts) in the SAME filing. Before this fix, the residual
"Revenues" figure won "revenue" unconditionally and was never corrected, producing an
~80x-11,000x understatement (and an outright $0 for FY2024) that fed
quarterly_revenue_sum_vs_annual_extreme's >10x-mismatch quarantine gate.

Fix: reit_exclusive_value_outranks_existing() (sec_reit_exclusive_scale_guard.py) lets a
REIT-exclusive concept overwrite an already-populated "revenue" only when the incoming value
is drastically LARGER (>=20x, i.e. the existing value is <5% of it) - a genuinely larger,
real already-populated total (the CLDT/MKZR shape covered by the sibling scale-mismatch test)
is never at risk, since this can only ever let a bigger, more complete figure win.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader


class TestReitExclusiveFieldOverridesResidualRevenue:
    def _make_loader(self, reit_symbols: frozenset[str]) -> SecEdgarStatementLoader:
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

    def test_nyc_shaped_residual_revenue_overridden_by_real_lease_income(self) -> None:
        loader = self._make_loader(reit_symbols=frozenset({"NYC"}))
        row = {
            "symbol": "NYC",
            "fiscal_year": 2024,
            "revenues": 0.0,
            "operating_lease_lease_income": 61_570_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["revenue"] == 61_570_000.0

    def test_nyc_shaped_near_zero_but_nonzero_residual_also_overridden(self) -> None:
        loader = self._make_loader(reit_symbols=frozenset({"NYC"}))
        row = {
            "symbol": "NYC",
            "fiscal_year": 2022,
            "revenues": 800_000.0,
            "operating_lease_lease_income": 64_005_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["revenue"] == 64_005_000.0

    def test_genuinely_larger_existing_total_still_protected(self) -> None:
        """A real, larger already-populated total (the CLDT/MKZR shape) must never be
        overridden - only a drastically smaller residual is."""
        loader = self._make_loader(reit_symbols=frozenset({"CLDT"}))
        row = {
            "symbol": "CLDT",
            "fiscal_year": 2025,
            "revenues": 295_871_000.0,
            "operating_lease_lease_income": 51_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["revenue"] == 295_871_000.0

    def test_modestly_smaller_existing_value_not_overridden(self) -> None:
        """Only a >=20x gap counts as the residual-fee-line anomaly - an existing value
        within an order of magnitude of the candidate is left alone."""
        loader = self._make_loader(reit_symbols=frozenset({"AAT"}))
        row = {
            "symbol": "AAT",
            "fiscal_year": 2024,
            "revenues": 30_000_000.0,
            "operating_lease_lease_income": 44_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["revenue"] == 30_000_000.0
