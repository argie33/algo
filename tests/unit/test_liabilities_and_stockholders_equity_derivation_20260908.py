"""Regression test for the 2026-09-08 fix (goal session: XBRL continuity gap triage follow-up -
scripts/triage_xbrl_continuity_gaps.py's SYNONYM_FOUND output for SEI Investments/BioRestorative/
Datacentrex/Edesa Biotech). Each filer stopped tagging plain "Liabilities" (and, for SEI's most
recent quarter, "Assets" too) while continuing to tag the standard cover-page total
"LiabilitiesAndStockholdersEquity" - a real, identity-guaranteed equivalent
(Assets = Liabilities + StockholdersEquity = LiabilitiesAndStockholdersEquity), not an estimate.

Live-confirmed via real companyfacts JSON: BioRestorative 2025-12-31 Assets=$4,079,635 exactly
equals that period's LiabilitiesAndStockholdersEquity fact, with StockholdersEquity=$356,744 -
Liabilities should derive to $3,722,891.
"""

from typing import Any

from utils.external.sec_balance_sheet import get_balance_sheet


class _FakeClient:
    def __init__(self, facts: dict[str, Any]) -> None:
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0000000000"

    def get_company_facts(self, cik: str) -> dict[str, Any]:
        return {"facts": self._facts}


def _entry(end: str, val: float, filed: str, form: str = "10-Q", fp: str = "Q4") -> dict[str, Any]:
    year = int(end[:4])
    return {"end": end, "val": val, "filed": filed, "fp": fp, "fy": year, "form": form}


class TestLiabilitiesFromAssetsMinusEquity:
    def test_liabilities_derived_when_only_liabilities_missing(self) -> None:
        facts = {
            "us-gaap": {
                "Assets": {"units": {"USD": [_entry("2025-12-31", 4_079_635.0, "2026-02-01")]}},
                "StockholdersEquity": {"units": {"USD": [_entry("2025-12-31", 356_744.0, "2026-02-01")]}},
                "LiabilitiesAndStockholdersEquity": {
                    "units": {"USD": [_entry("2025-12-31", 4_079_635.0, "2026-02-01")]}
                },
            },
            "ifrs-full": {},
        }
        rows = get_balance_sheet(_FakeClient(facts), "BRTX", period="quarterly")
        by_period = {(r["fiscal_year"], r["fiscal_period"]): r for r in rows}
        row = by_period[(2025, "Q4")]
        assert row["assets"] == 4_079_635.0
        assert row["liabilities"] == 3_722_891.0

    def test_both_assets_and_liabilities_derived_when_both_missing(self) -> None:
        facts = {
            "us-gaap": {
                "StockholdersEquity": {
                    "units": {"USD": [_entry("2026-06-30", 2_499_698_000.0, "2026-08-10", fp="Q2")]}
                },
                "LiabilitiesAndStockholdersEquity": {
                    "units": {"USD": [_entry("2026-06-30", 3_324_338_000.0, "2026-08-10", fp="Q2")]}
                },
            },
            "ifrs-full": {},
        }
        rows = get_balance_sheet(_FakeClient(facts), "SEIC", period="quarterly")
        by_period = {(r["fiscal_year"], r["fiscal_period"]): r for r in rows}
        row = by_period[(2026, "Q2")]
        assert row["assets"] == 3_324_338_000.0
        assert row["liabilities"] == 824_640_000.0

    def test_real_liabilities_never_overwritten(self) -> None:
        facts = {
            "us-gaap": {
                "Assets": {"units": {"USD": [_entry("2025-06-30", 8_516_559.0, "2025-08-10", fp="Q2")]}},
                "Liabilities": {"units": {"USD": [_entry("2025-06-30", 3_671_235.0, "2025-08-10", fp="Q2")]}},
                "StockholdersEquity": {"units": {"USD": [_entry("2025-06-30", 4_845_324.0, "2025-08-10", fp="Q2")]}},
                "LiabilitiesAndStockholdersEquity": {
                    "units": {"USD": [_entry("2025-06-30", 999_999_999.0, "2025-08-10", fp="Q2")]}
                },
            },
            "ifrs-full": {},
        }
        rows = get_balance_sheet(_FakeClient(facts), "BRTX", period="quarterly")
        by_period = {(r["fiscal_year"], r["fiscal_period"]): r for r in rows}
        row = by_period[(2025, "Q2")]
        assert row["liabilities"] == 3_671_235.0

    def test_no_combined_concept_leaves_gap_untouched(self) -> None:
        facts = {
            "us-gaap": {
                "Assets": {"units": {"USD": [_entry("2025-12-31", 1_000_000.0, "2026-02-01")]}},
                "StockholdersEquity": {"units": {"USD": [_entry("2025-12-31", 400_000.0, "2026-02-01")]}},
            },
            "ifrs-full": {},
        }
        rows = get_balance_sheet(_FakeClient(facts), "PLAINCO", period="quarterly")
        by_period = {(r["fiscal_year"], r["fiscal_period"]): r for r in rows}
        row = by_period[(2025, "Q4")]
        assert row.get("liabilities") is None
