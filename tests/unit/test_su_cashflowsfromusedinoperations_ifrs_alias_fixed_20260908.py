"""Regression test for the 2026-09-08 fix (goal session: "Missing SEC/XBRL data" 993 sweep,
dcf_fcf/fcf_margin "missing_cash_flow_data" investigation): SU (Suncor Energy, $50B+ Canadian
oil major, 40-F/IFRS filer) and several other 20-F/40-F filers (GLDG/SLI/SLSR/LPA/CDRO) tag
neither "CashFlowsFromUsedInOperatingActivities" nor the "...ContinuingOperations" variant -
live-confirmed real operating cash flow is only reported as "CashFlowsFromUsedInOperations"
(SU FY2025: CAD 12,781,000,000), with no separate tax-paid line to subtract from it (unlike
NGG, which tags a proper post-tax concept directly and never needed this fallback).
"""

from typing import Any

from loaders.load_financial_statements import _CASHFLOW_FIELD_MAPPING
from utils.external.sec_statements import _CASHFLOW_IFRS_ALIASES, _to_snake, get_cash_flow


class _FakeClient:
    def __init__(self, facts: dict[str, Any]) -> None:
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0000311337"

    def get_company_facts(self, cik: str) -> dict[str, Any]:
        return {"facts": self._facts}


def _entry(year: int, val: float, filed: str, form: str = "40-F", end: str | None = None) -> dict[str, Any]:
    return {"end": end or f"{year}-12-31", "val": val, "filed": filed, "fp": "FY", "fy": year, "form": form}


class TestSuCashFlowsFromUsedInOperationsIfrsAliasFixed:
    def test_alias_registered_and_routes_to_operating_cash_flow_column(self) -> None:
        target_key = _to_snake("NetCashProvidedByUsedInOperatingActivities")
        assert ("CashFlowsFromUsedInOperations", "net_cash_provided_by_used_in_operating_activities") in (
            _CASHFLOW_IFRS_ALIASES
        )
        assert _CASHFLOW_FIELD_MAPPING[target_key] == "operating_cash_flow"

    def test_su_style_concept_maps_through_get_cash_flow(self) -> None:
        facts = {
            "us-gaap": {},
            "ifrs-full": {
                "CashFlowsFromUsedInOperations": {
                    "units": {
                        "USD": [
                            _entry(2024, 15_960_000_000.0, "2025-02-25"),
                            _entry(2025, 12_781_000_000.0, "2026-02-24"),
                        ]
                    }
                },
            },
        }
        rows = get_cash_flow(_FakeClient(facts), "SU", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}
        assert by_year[2024]["net_cash_provided_by_used_in_operating_activities"] == 15_960_000_000.0
        assert by_year[2025]["net_cash_provided_by_used_in_operating_activities"] == 12_781_000_000.0

    def test_more_precise_concept_wins_when_filer_reports_both(self) -> None:
        # CashFlowsFromUsedInOperations must never overwrite the more precise/final
        # concepts above it in the alias list - it only fills the gap when both are
        # absent (lowest-priority fallback, listed last).
        facts = {
            "us-gaap": {},
            "ifrs-full": {
                "CashFlowsFromUsedInOperations": {"units": {"USD": [_entry(2025, 12_781_000_000.0, "2026-02-24")]}},
                "CashFlowsFromUsedInOperatingActivities": {
                    "units": {"USD": [_entry(2025, 12_500_000_000.0, "2026-02-24")]}
                },
            },
        }
        rows = get_cash_flow(_FakeClient(facts), "SU", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}
        assert by_year[2025]["net_cash_provided_by_used_in_operating_activities"] == 12_500_000_000.0
