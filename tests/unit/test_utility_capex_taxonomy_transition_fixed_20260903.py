"""Regression test for the 2026-09-03 fix (goal session: "missing SEC/XBRL data under 6k"
sweep, capex_never_tagged_in_recent_filings continuation): two large-cap regulated
utilities stopped tagging "PaymentsToAcquirePropertyPlantAndEquipment" in recent fiscal
years, each switching to a different replacement concept with different overwrite
semantics.

D (Dominion Energy, CIK 715957): "PaymentsForProceedsFromProductiveAssets" is a pure
taxonomy relabeling - live-confirmed via real companyfacts JSON that both concepts report
IDENTICAL values in every year both are tagged (FY2017 $5,909,000,000 under either
concept), then the new concept continues alone with real, growing values through FY2025
($12,653,000,000) while the old concept goes silent after FY2019. Safe as a plain
(non-fallback) concept.

ED (Consolidated Edison, CIK 1047862): "PaymentsForConstructionInProcess" is NOT a
relabeling - live-confirmed the two concepts report genuinely DIFFERENT values in years
both are tagged (FY2020: $3,326,000,000 this concept vs. $4,085,000,000 standard concept),
a narrower "construction work in progress" sub-line, not the full capex total. Must be
fallback-only so it only fills FY2023+ (where the standard concept goes silent) and never
overwrites the standard concept's more complete figure in years both exist.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader
from loaders.load_financial_statements import _CASHFLOW_FIELD_MAPPING, _SBC_BUYBACK_FALLBACK_ONLY_FIELDS


class TestUtilityCapexTaxonomyTransitionFixed:
    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_cash_flow"
        loader.period = "annual"
        loader.statement_type = "cashflow"
        loader._schema_cols = frozenset(
            {"symbol", "fiscal_year", "capex", "operating_cash_flow", "data_unavailable", "reason"}
        )
        loader._field_mapping = {
            "net_cash_provided_by_used_in_operating_activities": "operating_cash_flow",
            "payments_to_acquire_property_plant_and_equipment": "capex",
            "payments_for_proceeds_from_productive_assets": "capex",
            "payments_for_construction_in_process": "capex",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset({"payments_for_construction_in_process"})
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        return loader

    def test_field_mapping_wires_both_concepts_to_capex(self) -> None:
        assert _CASHFLOW_FIELD_MAPPING["payments_for_proceeds_from_productive_assets"] == "capex"
        assert _CASHFLOW_FIELD_MAPPING["payments_for_construction_in_process"] == "capex"
        assert "payments_for_construction_in_process" in _SBC_BUYBACK_FALLBACK_ONLY_FIELDS

    def test_d_style_relabeled_concept_recovered_when_standard_concept_absent(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "D",
            "fiscal_year": 2024,
            "payments_for_proceeds_from_productive_assets": 12_427_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["capex"] == 12_427_000_000.0

    def test_ed_style_fallback_does_not_overwrite_real_standard_concept(self) -> None:
        # Both concepts present for the same fiscal year (ED's FY2020 shape) - the
        # narrower construction-in-process figure must never win over the real total.
        loader = self._make_loader()
        row = {
            "symbol": "ED",
            "fiscal_year": 2020,
            "payments_to_acquire_property_plant_and_equipment": 4_085_000_000.0,
            "payments_for_construction_in_process": 3_326_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["capex"] == 4_085_000_000.0

    def test_ed_style_fallback_fills_gap_when_standard_concept_absent(self) -> None:
        # ED's FY2023+ shape: standard concept genuinely absent, fallback must still
        # recover real data instead of leaving capex NULL.
        loader = self._make_loader()
        row = {
            "symbol": "ED",
            "fiscal_year": 2023,
            "payments_for_construction_in_process": 4_353_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["capex"] == 4_353_000_000.0
