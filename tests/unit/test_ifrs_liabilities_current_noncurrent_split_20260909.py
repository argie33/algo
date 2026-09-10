"""Regression test for the 2026-09-09 fix (goal session: XBRL continuity checker follow-up,
right after the FPI scanning-coverage fix surfaced this filer for the first time - see
scripts/xbrl_concept_continuity_scan.py output). HUB Cyber Security Ltd. (CIK 0001905660) tags
ifrs-full:CurrentLiabilities and ifrs-full:NoncurrentLiabilities for FY2024 but never tags the
combined ifrs-full:Liabilities total for that period at all - previously left NULL.

Live-confirmed via real companyfacts JSON: FY2024 (period end 2024-12-31)
CurrentLiabilities=USD 106,074,000 + NoncurrentLiabilities=USD 2,159,000 = USD 108,233,000,
exactly matching that same filing's directly-tagged EquityAndLiabilities (USD 27,416,000) minus
Equity (USD -80,817,000) - confirms this is the real total, not a partial figure.
"""

from typing import Any

from utils.external.sec_balance_sheet import get_balance_sheet


class _FakeClient:
    def __init__(self, facts: dict[str, Any]) -> None:
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0001905660"

    def get_company_facts(self, cik: str) -> dict[str, Any]:
        return {"facts": self._facts}


def _entry(end: str, val: float, filed: str, form: str = "20-F", fp: str = "FY") -> dict[str, Any]:
    year = int(end[:4])
    return {"end": end, "val": val, "filed": filed, "fp": fp, "fy": year, "form": form}


class TestLiabilitiesFromIfrsCurrentNoncurrentSplit:
    def test_liabilities_derived_from_current_plus_noncurrent(self) -> None:
        facts = {
            "us-gaap": {},
            "ifrs-full": {
                "CurrentLiabilities": {"units": {"USD": [_entry("2024-12-31", 106_074_000.0, "2025-04-01")]}},
                "NoncurrentLiabilities": {"units": {"USD": [_entry("2024-12-31", 2_159_000.0, "2025-04-01")]}},
            },
        }
        rows = get_balance_sheet(_FakeClient(facts), "HUBC", period="annual")
        by_period = {(r["fiscal_year"], r["fiscal_period"]): r for r in rows}
        row = by_period[(2024, "FY")]
        assert row["liabilities"] == 108_233_000.0

    def test_real_liabilities_never_overwritten(self) -> None:
        facts = {
            "us-gaap": {},
            "ifrs-full": {
                "Liabilities": {"units": {"USD": [_entry("2024-12-31", 999_999_999.0, "2025-04-01")]}},
                "CurrentLiabilities": {"units": {"USD": [_entry("2024-12-31", 106_074_000.0, "2025-04-01")]}},
                "NoncurrentLiabilities": {"units": {"USD": [_entry("2024-12-31", 2_159_000.0, "2025-04-01")]}},
            },
        }
        rows = get_balance_sheet(_FakeClient(facts), "HUBC", period="annual")
        by_period = {(r["fiscal_year"], r["fiscal_period"]): r for r in rows}
        row = by_period[(2024, "FY")]
        assert row["liabilities"] == 999_999_999.0

    def test_only_current_half_present_leaves_gap_untouched(self) -> None:
        facts = {
            "us-gaap": {},
            "ifrs-full": {
                "CurrentLiabilities": {"units": {"USD": [_entry("2024-12-31", 106_074_000.0, "2025-04-01")]}},
            },
        }
        rows = get_balance_sheet(_FakeClient(facts), "HUBC", period="annual")
        by_period = {(r["fiscal_year"], r["fiscal_period"]): r for r in rows}
        row = by_period[(2024, "FY")]
        assert row.get("liabilities") is None
