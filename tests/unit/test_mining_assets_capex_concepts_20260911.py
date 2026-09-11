"""Regression test for the 2026-09-11 fix (goal: "SEC/XBRL missing data under 300" push,
found via scripts/xbrl_concept_coverage_scan.py rather than a one-off bug report):
us-gaap:PaymentsToAcquireMiningAssets (27 real filers, e.g. CleanSpark, McEwen Inc, Idaho
Strategic Resources, Materion Corporation) and its IFRS sibling
ifrs-full:PurchaseOfMiningAssets (15 real filers, e.g. Fortuna Silver Mines/FSM) were never
in sec_cash_flow.py's capex fetch allowlist at all, leaving mining-sector filers' real,
current capex NULL ("capex_never_tagged_in_recent_filings") despite the data existing on
SEC EDGAR.
"""

from typing import Any

from loaders.load_financial_statements import _CASHFLOW_FIELD_MAPPING
from utils.external.sec_statements import _CASHFLOW_IFRS_ALIASES, _to_snake, get_cash_flow


class _FakeClient:
    def __init__(self, facts: dict[str, Any]) -> None:
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0001341335"

    def get_company_facts(self, cik: str) -> dict[str, Any]:
        return {"facts": self._facts}


def _entry(year: int, val: float, filed: str, form: str = "10-K") -> dict[str, Any]:
    return {"end": f"{year}-12-31", "val": val, "filed": filed, "fp": "FY", "fy": year, "form": form}


class TestPaymentsToAcquireMiningAssetsUsGaap:
    def test_field_mapping_routes_to_capex_column(self) -> None:
        assert _CASHFLOW_FIELD_MAPPING[_to_snake("PaymentsToAcquireMiningAssets")] == "capex"

    def test_maps_through_get_cash_flow(self) -> None:
        facts = {
            "us-gaap": {
                "PaymentsToAcquireMiningAssets": {
                    "units": {"USD": [_entry(2025, 382_285_000.0, "2026-08-07")]},
                },
            },
            "ifrs-full": {},
        }
        rows = get_cash_flow(_FakeClient(facts), "CLSK", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}
        assert by_year[2025]["payments_to_acquire_mining_assets"] == 382_285_000.0


class TestPurchaseOfMiningAssetsIfrs:
    def test_alias_registered(self) -> None:
        target_key = _to_snake("PaymentsToAcquirePropertyPlantAndEquipment")
        assert ("PurchaseOfMiningAssets", target_key) in _CASHFLOW_IFRS_ALIASES
        assert _CASHFLOW_FIELD_MAPPING[target_key] == "capex"

    def test_fsm_style_concept_maps_through_get_cash_flow(self) -> None:
        facts = {
            "us-gaap": {},
            "ifrs-full": {
                "PurchaseOfMiningAssets": {
                    "units": {"USD": [_entry(2025, 178_004_000.0, "2026-03-26", form="40-F")]},
                },
            },
        }
        rows = get_cash_flow(_FakeClient(facts), "FSM", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}
        assert by_year[2025]["payments_to_acquire_property_plant_and_equipment"] == 178_004_000.0
