"""Regression test for the 2026-09-10 IFRS "PropertyPlantAndEquipmentIncludingRightofuseAssets"
alias (goal: "missing SEC/XBRL data under 300" push, dcf_fcf capex_never_tagged investigation).

FSM (Fortuna Silver Mines, a 40-F filer) tagged plain "PropertyPlantAndEquipment" through
FY2022 then switched to this right-of-use-inclusive variant starting FY2023 - live-confirmed
via its real companyfacts JSON (CIK 0001341335): FY2022 $1,567,622,000 (bare concept) vs.
FY2023 $1,574,212,000 (new concept) - a plausible, similar-magnitude successor figure, not a
scope blowup. Left ppe_net NULL for 3 straight real fiscal years, silently blocking
annual_cash_flow's PPE-delta capex derivation even though depreciation_expense was extracted
fine every year.
"""

from typing import Any

from utils.external.sec_balance_sheet import get_balance_sheet


class _FakeClient:
    def __init__(self, facts: dict[str, Any]) -> None:
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0001341335"

    def get_company_facts(self, cik: str) -> dict[str, Any]:
        return {"facts": self._facts}


def _entry(year: int, val: float, filed: str, form: str = "40-F") -> dict[str, Any]:
    return {"end": f"{year}-12-31", "val": val, "filed": filed, "fp": "FY", "fy": year, "form": form}


class TestIfrsPpeIncludingRouAssetsAlias:
    def test_including_rou_assets_maps_to_ppe_net(self) -> None:
        facts = {
            "us-gaap": {},
            "ifrs-full": {
                "Assets": {"units": {"USD": [_entry(2023, 5_000_000_000.0, "2024-03-15")]}},
                "PropertyPlantAndEquipmentIncludingRightofuseAssets": {
                    "units": {"USD": [_entry(2023, 1_574_212_000.0, "2024-03-15")]}
                },
            },
        }
        rows = get_balance_sheet(_FakeClient(facts), "FSM", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}
        assert by_year[2023]["property_plant_and_equipment_net"] == 1_574_212_000.0

    def test_bare_property_plant_and_equipment_wins_when_both_present(self) -> None:
        facts = {
            "us-gaap": {},
            "ifrs-full": {
                "Assets": {"units": {"USD": [_entry(2022, 5_000_000_000.0, "2023-03-01")]}},
                "PropertyPlantAndEquipment": {"units": {"USD": [_entry(2022, 1_567_622_000.0, "2023-03-01")]}},
                "PropertyPlantAndEquipmentIncludingRightofuseAssets": {
                    "units": {"USD": [_entry(2022, 1_800_000_000.0, "2023-03-01")]}
                },
            },
        }
        rows = get_balance_sheet(_FakeClient(facts), "FSM", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}
        assert by_year[2022]["property_plant_and_equipment_net"] == 1_567_622_000.0
