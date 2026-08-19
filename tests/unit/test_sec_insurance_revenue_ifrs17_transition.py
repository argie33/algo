"""Regression test for the IFRS 17 insurance-revenue transition gap found live 2026-08-19
(goal: "no SEC data"/loader audit, roic_pct/AEG follow-up).

Aegon (AEG) live-confirmed via real companyfacts JSON: tags "Revenue" through FY2022 (EUR
21.33B), then goes silent - "InsuranceRevenue" (the IFRS 17 concept, effective FY2023 for
most insurers) takes over from FY2023 onward. Before this fix, annual_income_statement.revenue
was NULL for AEG's 3 most recent fiscal years despite complete, real balance-sheet and
income-statement data otherwise - this fed into load_value_quality_growth_metrics.py's
anchor-fiscal-year-selection query (which strongly prefers a fiscal year with non-NULL
revenue), silently picking a stale FY2022 anchor over the real, current FY2025 data and
masking every quality_metrics field for AEG behind a generic reason.

The first version of this fix made "revenues" fallback-only (mirroring the gold-revenue
precedent) - live-caught as WRONG before shipping: unlike RevenueFromSaleOfGold's target
("sales_revenue_goods_net", a fill-only-if-empty secondary field), "revenues" is the PRIMARY
revenue field several weaker concepts (interest_income_operating,
interest_and_dividend_income_operating, ...) also map to the same "revenue" DB column as a
last-resort fallback. Making "revenues" itself fallback-only meant any of those weaker
fields could populate "revenue" FIRST and then permanently block the real InsuranceRevenue
value from ever overwriting it. "revenues" must stay a normal, always-processed field -
_aggregate_concepts's own per-fiscal-year merge already resolves Revenue vs. InsuranceRevenue
correctly with no ambiguity (temporally exclusive for a given fiscal year).
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader


class TestInsuranceRevenueTransition:
    def _make_loader(self):
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_income_statement"
        loader.period = "annual"
        loader.statement_type = "income"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "revenue", "data_unavailable", "reason"})
        loader._field_mapping = {
            "revenues": "revenue",
            "interest_income_operating": "revenue",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset({"interest_income_operating"})
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        return loader

    def test_insurance_revenue_derived_value_populates_revenue(self):
        """ "revenues" (whether sourced from "Revenue" or the IFRS 17 "InsuranceRevenue"
        alias - both resolve to the same "revenues" key before this stage) must be a
        normal, always-processed field, not fallback-only."""
        loader = self._make_loader()
        row = {
            "symbol": "AEG",
            "fiscal_year": 2023,
            "revenues": 11_476_496_718.16,
        }

        transformed = loader.transform([row])

        assert transformed[0]["revenue"] == 11_476_496_718.16

    def test_insurance_revenue_derived_value_not_blocked_by_a_weaker_fallback_field(self):
        """The live-caught bug: if a weaker fallback field (interest_income_operating)
        happens to populate "revenue" first, "revenues" must still win - it is NOT itself
        fallback-only, so it always overwrites a weaker same-target field."""
        loader = self._make_loader()
        row = {
            "symbol": "AEG",
            "fiscal_year": 2023,
            "interest_income_operating": 5_000_000.0,
            "revenues": 11_476_496_718.16,
        }

        transformed = loader.transform([row])

        assert transformed[0]["revenue"] == 11_476_496_718.16
