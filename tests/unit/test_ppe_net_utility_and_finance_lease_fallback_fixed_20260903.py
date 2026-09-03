"""Regression test for the 2026-09-03 fix (goal session: "missing SEC/XBRL data under 6k"
sweep, ppe_net gap investigation): two fallback-only concepts for filers that never tag the
standard "PropertyPlantAndEquipmentNet" concept.

Live-confirmed via real companyfacts JSON:
- ES (Eversource, regulated utility): entire net PP&E under the utility-specific
  "PublicUtilitiesPropertyPlantAndEquipmentNet" concept - $39,498,607,000 FY2023 /
  $40,986,578,000 FY2024 / $45,930,959,000 FY2025, continuous. A live DB scan found 11
  Utilities-sector symbols (ES/TXNM/AVA/CWT/SWX/MSEX/RGCO among others) with real
  total_assets but never a single ppe_net value across any fiscal year.
- DASH (DoorDash) and DINO (HF Sinclair): entire net PP&E under the post-ASC-842 combined
  "PropertyPlantAndEquipmentAndFinanceLeaseRightOfUseAssetAfterAccumulatedDepreciationAnd
  Amortization" concept - DASH $778,000,000 FY2024/$1,067,000,000 FY2025, DINO
  $6,627,000,000 FY2023/$6,558,000,000 FY2024/$6,533,000,000 FY2025.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader
from loaders.load_financial_statements import _BALANCE_FIELD_MAPPING, _DEBT_FALLBACK_ONLY_FIELDS

_COMBINED_LEASE_KEY = (
    "property_plant_and_equipment_and_finance_lease_right_of_use_asset_after_accumulated_depreciation_and_amortization"
)


class TestPpeNetUtilityAndFinanceLeaseFallbackFixed:
    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_balance_sheet"
        loader.period = "annual"
        loader.statement_type = "balance"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "ppe_net", "data_unavailable", "reason"})
        loader._field_mapping = {
            "ppe_net": "ppe_net",
            "property_plant_and_equipment_net": "ppe_net",
            "public_utilities_property_plant_and_equipment_net": "ppe_net",
            _COMBINED_LEASE_KEY: "ppe_net",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset(
            {"public_utilities_property_plant_and_equipment_net", _COMBINED_LEASE_KEY}
        )
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        return loader

    def test_field_mapping_wires_both_fallbacks_to_ppe_net(self) -> None:
        assert _BALANCE_FIELD_MAPPING["public_utilities_property_plant_and_equipment_net"] == "ppe_net"
        assert _BALANCE_FIELD_MAPPING[_COMBINED_LEASE_KEY] == "ppe_net"
        assert "public_utilities_property_plant_and_equipment_net" in _DEBT_FALLBACK_ONLY_FIELDS
        assert _COMBINED_LEASE_KEY in _DEBT_FALLBACK_ONLY_FIELDS

    def test_es_style_ppe_net_recovered_from_utility_concept(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "ES",
            "fiscal_year": 2025,
            "public_utilities_property_plant_and_equipment_net": 45_930_959_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["ppe_net"] == 45_930_959_000.0

    def test_dash_style_ppe_net_recovered_from_combined_lease_concept(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "DASH",
            "fiscal_year": 2025,
            _COMBINED_LEASE_KEY: 1_067_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["ppe_net"] == 1_067_000_000.0

    def test_fallback_concepts_never_overwrite_the_standard_concept(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "AAPL",
            "fiscal_year": 2025,
            "property_plant_and_equipment_net": 45_680_000_000.0,
            "public_utilities_property_plant_and_equipment_net": 1.0,
            _COMBINED_LEASE_KEY: 2.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["ppe_net"] == 45_680_000_000.0
