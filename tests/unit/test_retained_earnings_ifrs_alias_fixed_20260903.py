"""Regression test for the 2026-09-03 fix (goal session: "missing SEC/XBRL data under 6k"
sweep): Altman Z''-Score's Retained Earnings/Total Assets term
("RetainedEarningsAccumulatedDeficit") is a us-gaap-only concept - went universally NULL
for every IFRS filer (20-F/40-F). Live-confirmed via real companyfacts JSON that the
equivalent ifrs-full concept is "RetainedEarnings" (7/9 large-cap IFRS filers checked have
it: AZN/SHEL/NVO/BHP/SAP/RY/HSBC; NVS/TTE genuinely don't tag it). TSM (Taiwan
Semiconductor) reports it directly in a usable USD unit alongside a TWD-unit series:
$118,114,500,000 as of FY2024, continuous 2018-2024.
"""

from typing import Any

from loaders.load_financial_statements import _ANNUAL_BALANCE_EXTRA
from utils.external.sec_statements import _BALANCE_IFRS_ALIASES, get_balance_sheet


class _FakeClient:
    def __init__(self, facts: dict[str, Any]) -> None:
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0000000000"

    def get_company_facts(self, cik: str) -> dict[str, Any]:
        return {"facts": self._facts}


def _entry(year: int, val: float, filed: str, form: str = "20-F") -> dict[str, Any]:
    return {"end": f"{year}-12-31", "val": val, "filed": filed, "fp": "FY", "fy": year, "form": form}


class TestRetainedEarningsIfrsAliasFixed:
    def test_alias_registered_and_routes_to_retained_earnings_column(self) -> None:
        assert ("RetainedEarnings", "retained_earnings_accumulated_deficit") in _BALANCE_IFRS_ALIASES
        assert _ANNUAL_BALANCE_EXTRA["retained_earnings_accumulated_deficit"] == "retained_earnings"

    def test_tsm_style_ifrs_retained_earnings_maps_through_get_balance_sheet(self) -> None:
        facts = {
            "us-gaap": {},
            "ifrs-full": {
                "RetainedEarnings": {
                    "units": {
                        "USD": [_entry(2024, 118_114_500_000.0, "2025-03-10")],
                        "TWD": [_entry(2024, 3_872_973_400_000.0, "2025-03-10")],
                    }
                },
            },
        }
        rows = get_balance_sheet(_FakeClient(facts), "TSM", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}
        assert by_year[2024]["retained_earnings_accumulated_deficit"] == 118_114_500_000.0
