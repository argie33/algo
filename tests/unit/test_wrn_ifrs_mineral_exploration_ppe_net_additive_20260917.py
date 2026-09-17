"""Regression test for the 2026-09-17 ppe_net cluster follow-up: IFRS filers' mining-explorer
equivalent of the already-fixed THM/PZG "MineralPropertiesNet" pattern (see
test_ppe_net_mining_oil_gas_sibling_concepts_20260917.py).

Live-confirmed via real SEC companyfacts JSON: WRN (West Red Lake Gold Mines, CIK 0001063341,
40-F filer) tags its entire real mineral-exploration asset under
"AssetsArisingFromExplorationForAndEvaluationOfMineralResources" every fiscal year on file
(FY2022 CAD 66,347,266, FY2023 CAD 83,441,561, FY2024 CAD 85,339,409, FY2025 CAD 105,590,591)
while "PropertyPlantAndEquipmentNet" is only a tiny residual corporate-equipment balance
(FY2025 CAD 33,809) - same additive shape as MineralPropertiesNet, just IFRS's own taxonomy
name for pre-production mineral-resource exploration/evaluation spend.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader
from loaders.load_financial_statements import _BALANCE_FIELD_MAPPING


class TestWrnIfrsMineralExplorationPpeNetAdditive:
    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_balance_sheet"
        loader.period = "annual"
        loader.statement_type = "balance"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "ppe_net", "data_unavailable", "reason"})
        loader._field_mapping = {
            "property_plant_and_equipment_net": "ppe_net",
            "assets_arising_from_exploration_for_and_evaluation_of_mineral_resources": "ppe_net",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset()
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        return loader

    def test_field_mapping_wired(self) -> None:
        assert (
            _BALANCE_FIELD_MAPPING["assets_arising_from_exploration_for_and_evaluation_of_mineral_resources"]
            == "ppe_net"
        )

    def test_wrn_style_mineral_exploration_asset_summed_not_overwritten(self) -> None:
        loader = self._make_loader()
        # Dict-insertion order matches the concept-list order (the IFRS exploration concept
        # listed before the plain concept): it's processed first, then
        # property_plant_and_equipment_net triggers the sum rather than overwriting it.
        row = {
            "symbol": "WRN",
            "fiscal_year": 2025,
            "assets_arising_from_exploration_for_and_evaluation_of_mineral_resources": 105_590_591.0,
            "property_plant_and_equipment_net": 33_808.79345603272,
        }

        transformed = loader.transform([row])

        assert transformed[0]["ppe_net"] == 105_624_399.79345603

    def test_solo_exploration_asset_still_fills_empty_field(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "SOMEEXPLORER",
            "fiscal_year": 2025,
            "assets_arising_from_exploration_for_and_evaluation_of_mineral_resources": 5_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["ppe_net"] == 5_000.0
