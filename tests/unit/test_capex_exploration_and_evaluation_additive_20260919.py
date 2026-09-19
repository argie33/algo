"""Regression test (2026-09-19, data-quality-issue-reduction goal session, xbrl_yfinance_
line_item_report capex cluster follow-up).

Live-confirmed via NVA (Nova Minerals Corp, CIK 0001852551) FY2022 (fiscal year ended
2022-06-30): real SEC companyfacts JSON tags "PurchaseOfPropertyPlantAndEquipment
ClassifiedAsInvestingActivities" (AUD 1,055,878, a small equipment-purchase line) AND
"PurchaseOfExplorationAndEvaluationAssets" (AUD 24,799,177, the dominant real capex line for
a pre-production mineral explorer) in the same fiscal year - genuinely distinct, additive
investing-activity cash outflows, not alternates. Both map to db_field "capex" via
field_mapping.

Before this fix, ADDITIVE_CONCEPT_PAIRS had no entry for
"purchase_of_exploration_and_evaluation_assets", so it fell through to the ordinary
last-listed-concept-wins rule and NVA's stored capex was stuck at the small equipment-only
figure (matching our_value in xbrl_yfinance_line_item_report exactly), understating real
capex by ~24x - the exact "our value 25-100x smaller than yfinance" shape flagged by that
crosscheck. Same root cause and fix mechanism as this filer's own ppe_net pair
("tangible_exploration_and_evaluation_assets", added 2026-09-17 - see
sec_zero_component_guards.py's ADDITIVE_CONCEPT_PAIRS comment).
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader


class TestCapexExplorationAndEvaluationAdditive:
    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_cash_flow"
        loader.period = "annual"
        loader.statement_type = "cash_flow"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "capex", "data_unavailable", "reason"})
        loader._field_mapping = {
            "purchase_of_property_plant_and_equipment_classified_as_investing_activities": "capex",
            "purchase_of_exploration_and_evaluation_assets": "capex",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset()
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_exclusive_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        return loader

    def test_ppe_and_exploration_purchases_sum_instead_of_overwrite(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "NVA",
            "fiscal_year": 2022,
            "purchase_of_property_plant_and_equipment_classified_as_investing_activities": 1_055_878.0,
            "_rank_purchase_of_property_plant_and_equipment_classified_as_investing_activities": 2,
            "purchase_of_exploration_and_evaluation_assets": 24_799_177.0,
            "_rank_purchase_of_exploration_and_evaluation_assets": 2,
        }

        transformed = loader.transform([row])

        assert transformed[0]["capex"] == 1_055_878.0 + 24_799_177.0
