"""Regression test for the 2026-09-10 fix (goal: "Missing SEC/XBRL data" under-500 push,
WPP/RTO live-confirmed). Mirrors the 2026-09-09 liabilities-side fix
(test_ifrs_liabilities_current_noncurrent_split_20260909.py) for the assets side of the same
gap class: an IFRS filer that tags CurrentAssets/NoncurrentAssets every fiscal year but never
tags the combined ifrs-full:Assets total at all.

Live-confirmed via real companyfacts JSON: WPP plc (CIK 0000806968, 341 cached ifrs-full
concepts) and Rentokil Initial plc (CIK 0000930157, 299 concepts) both have this exact shape -
CurrentAssets and NoncurrentAssets present every year, plain "Assets" absent entirely - leaving
total_assets (and everything derived from it: asset_turnover, roa, gross_profitability)
permanently NULL despite a complete, extractable filing.
"""

from typing import Any

from utils.external.sec_balance_sheet import get_balance_sheet


class _FakeClient:
    def __init__(self, facts: dict[str, Any]) -> None:
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0000806968"

    def get_company_facts(self, cik: str) -> dict[str, Any]:
        return {"facts": self._facts}


def _entry(end: str, val: float, filed: str, form: str = "20-F", fp: str = "FY") -> dict[str, Any]:
    year = int(end[:4])
    return {"end": end, "val": val, "filed": filed, "fp": fp, "fy": year, "form": form}


class TestAssetsFromIfrsCurrentNoncurrentSplit:
    def test_assets_derived_from_current_plus_noncurrent(self) -> None:
        facts = {
            "us-gaap": {},
            "ifrs-full": {
                "CurrentAssets": {"units": {"USD": [_entry("2025-12-31", 17_734_029_947.21534, "2026-03-01")]}},
                "NoncurrentAssets": {"units": {"USD": [_entry("2025-12-31", 14_684_099_967.68286, "2026-03-01")]}},
            },
        }
        rows = get_balance_sheet(_FakeClient(facts), "WPP", period="annual")
        by_period = {(r["fiscal_year"], r["fiscal_period"]): r for r in rows}
        row = by_period[(2025, "FY")]
        assert row["assets"] == 17_734_029_947.21534 + 14_684_099_967.68286

    def test_real_assets_never_overwritten(self) -> None:
        facts = {
            "us-gaap": {},
            "ifrs-full": {
                "Assets": {"units": {"USD": [_entry("2025-12-31", 999_999_999.0, "2026-03-01")]}},
                "CurrentAssets": {"units": {"USD": [_entry("2025-12-31", 17_734_029_947.21534, "2026-03-01")]}},
                "NoncurrentAssets": {"units": {"USD": [_entry("2025-12-31", 14_684_099_967.68286, "2026-03-01")]}},
            },
        }
        rows = get_balance_sheet(_FakeClient(facts), "WPP", period="annual")
        by_period = {(r["fiscal_year"], r["fiscal_period"]): r for r in rows}
        row = by_period[(2025, "FY")]
        assert row["assets"] == 999_999_999.0

    def test_only_current_half_present_leaves_gap_untouched(self) -> None:
        facts = {
            "us-gaap": {},
            "ifrs-full": {
                "CurrentAssets": {"units": {"USD": [_entry("2025-12-31", 17_734_029_947.21534, "2026-03-01")]}},
            },
        }
        rows = get_balance_sheet(_FakeClient(facts), "WPP", period="annual")
        by_period = {(r["fiscal_year"], r["fiscal_period"]): r for r in rows}
        row = by_period[(2025, "FY")]
        assert row.get("assets") is None
