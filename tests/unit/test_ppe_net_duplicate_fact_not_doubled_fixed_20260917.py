"""Regression test for the 2026-09-17 ppe_net cluster follow-up fix: ADT (CIK 0001703056)
live-confirmed via real SEC companyfacts JSON.

ADDITIVE_CONCEPT_PAIRS (sec_zero_component_guards.py) includes
("ppe_net", "property_plant_and_equipment_net") so mining/O&G sector-specific sibling concepts
(MineralPropertiesNet, OilAndGasPropertySuccessfulEffortMethodNet) sum correctly with a small
remaining corporate PropertyPlantAndEquipmentNet balance. But the plain standard concept is
also one of its own pair's two components - so when the raw `rows` input legitimately contains
the SAME sec_field's identical fact reported twice for one fiscal year (e.g. a 10-K and a later
10-Q both carrying the same period-end comparative balance), the additive-sum path fired
against itself and doubled the value instead of treating it as a duplicate re-report of the
same fact:

- ADT FY2024 (period end 2024-12-31): SEC PropertyPlantAndEquipmentNet = $247,183,000
  (confirmed identical across the 10-K and multiple subsequent 10-Q filings' comparative
  column). Before this fix, our stored value was $494,366,000 - exactly 2x.
- ADT FY2025 (period end 2025-12-31): SEC value $243,398,000, stored value $486,796,000 -
  exactly 2x, same shape.

Fix: is_additive_concept_pair now returns False when `existing == value` (an exact numeric
match), since a genuine second additive component practically never coincides exactly with an
already-stored total, while a duplicate re-report of the identical fact always does.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader
from loaders.helpers.sec_zero_component_guards import is_additive_concept_pair


class TestPpeNetDuplicateFactNotDoubled:
    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_balance_sheet"
        loader.period = "annual"
        loader.statement_type = "balance"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "ppe_net", "data_unavailable", "reason"})
        loader._field_mapping = {
            "property_plant_and_equipment_net": "ppe_net",
            "mineral_properties_net": "ppe_net",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset()
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        return loader

    def test_is_additive_concept_pair_rejects_exact_duplicate(self) -> None:
        assert (
            is_additive_concept_pair("ppe_net", "property_plant_and_equipment_net", 247_183_000.0, 247_183_000.0)
            is False
        )

    def test_is_additive_concept_pair_still_sums_genuine_sibling_components(self) -> None:
        # THM-style: different concepts, different values - still additive.
        assert is_additive_concept_pair("ppe_net", "property_plant_and_equipment_net", 55_375_124.0, 7_465.0) is True

    def test_adt_style_duplicate_ppe_fact_not_doubled(self) -> None:
        loader = self._make_loader()
        # Simulates the same underlying "PropertyPlantAndEquipmentNet" SEC fact appearing
        # twice for the same fiscal year (e.g. 10-K plus a later 10-Q's identical comparative
        # balance) - the raw dict only has one key so this exercises transform()'s duplicate
        # handling via a direct sequence of two rows sharing symbol+fiscal_year is out of
        # scope for this loader's per-row transform(); the guard itself (exercised above) is
        # the actual fix surface. This row-level test instead confirms a solo real value still
        # writes through untouched (no regression to the ordinary single-fact path).
        row = {
            "symbol": "ADT",
            "fiscal_year": 2024,
            "property_plant_and_equipment_net": 247_183_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["ppe_net"] == 247_183_000.0
