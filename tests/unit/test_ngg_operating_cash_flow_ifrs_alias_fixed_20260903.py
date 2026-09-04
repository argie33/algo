"""Regression test for the 2026-09-03 fix (goal session: "missing SEC/XBRL data under 6k"
sweep, free_cash_flow/fcf_margin/accruals_ratio investigation): NGG (National Grid plc,
$78.5B UK utility, 20-F/IFRS filer) never tags plain "CashFlowsFromUsedInOperatingActivities"
- live-confirmed real operating cash flow is only reported as
"CashFlowsFromUsedInOperatingActivitiesContinuingOperations" (GBP 6,939,000,000 FY2024 /
6,808,000,000 FY2025). annual_cash_flow.capex was already populated for NGG via a separate
concept, but operating_cash_flow being permanently NULL blocked free_cash_flow and everything
computed from it (fcf_margin, accruals_ratio, fcf_yield, fcf_to_net_income).
"""

from typing import Any

from loaders.load_financial_statements import _CASHFLOW_FIELD_MAPPING
from utils.external.sec_statements import _CASHFLOW_IFRS_ALIASES, _to_snake, get_cash_flow


class _FakeClient:
    def __init__(self, facts: dict[str, Any]) -> None:
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0000000000"

    def get_company_facts(self, cik: str) -> dict[str, Any]:
        return {"facts": self._facts}


def _entry(year: int, val: float, filed: str, form: str = "20-F", end: str | None = None) -> dict[str, Any]:
    return {"end": end or f"{year}-12-31", "val": val, "filed": filed, "fp": "FY", "fy": year, "form": form}


class TestNggOperatingCashFlowIfrsAliasFixed:
    def test_alias_registered_and_routes_to_operating_cash_flow_column(self) -> None:
        target_key = _to_snake("NetCashProvidedByUsedInOperatingActivities")
        assert (
            "CashFlowsFromUsedInOperatingActivitiesContinuingOperations",
            "net_cash_provided_by_used_in_operating_activities",
        ) in _CASHFLOW_IFRS_ALIASES
        assert target_key == "net_cash_provided_by_used_in_operating_activities"
        assert _CASHFLOW_FIELD_MAPPING[target_key] == "operating_cash_flow"

    def test_ngg_style_continuing_operations_concept_maps_through_get_cash_flow(self) -> None:
        # Uses a USD-denominated fixture (unlike NGG's real GBP-only reporting) to test the
        # alias/target_key wiring in isolation, without also exercising FX conversion -
        # same "USD unit sidesteps FX conversion for a cleaner test" precedent as
        # test_retained_earnings_ifrs_alias_fixed_20260903.py's TSM fixture.
        facts = {
            "us-gaap": {},
            "ifrs-full": {
                "CashFlowsFromUsedInOperatingActivitiesContinuingOperations": {
                    "units": {
                        "USD": [
                            _entry(2024, 6_939_000_000.0, "2024-05-15", end="2024-03-31"),
                            _entry(2025, 6_808_000_000.0, "2025-05-15", end="2025-03-31"),
                        ]
                    }
                },
            },
        }
        rows = get_cash_flow(_FakeClient(facts), "NGG", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}
        assert by_year[2024]["net_cash_provided_by_used_in_operating_activities"] == 6_939_000_000.0
        assert by_year[2025]["net_cash_provided_by_used_in_operating_activities"] == 6_808_000_000.0

    def test_plain_concept_wins_when_filer_reports_both(self) -> None:
        # The continuing-operations variant must never overwrite the broader plain total
        # for a filer that reports both - it only fills the gap when the plain concept is
        # absent entirely (this file's "last-listed wins" convention: the plain concept is
        # listed after the continuing-operations alias in _CASHFLOW_IFRS_ALIASES).
        facts = {
            "us-gaap": {},
            "ifrs-full": {
                "CashFlowsFromUsedInOperatingActivitiesContinuingOperations": {
                    "units": {"USD": [_entry(2024, 6_939_000_000.0, "2024-05-15", end="2024-03-31")]}
                },
                "CashFlowsFromUsedInOperatingActivities": {
                    "units": {"USD": [_entry(2024, 7_100_000_000.0, "2024-05-15", end="2024-03-31")]}
                },
            },
        }
        rows = get_cash_flow(_FakeClient(facts), "NGG", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}
        assert by_year[2024]["net_cash_provided_by_used_in_operating_activities"] == 7_100_000_000.0
