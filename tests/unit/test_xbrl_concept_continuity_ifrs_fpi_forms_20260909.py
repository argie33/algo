"""Regression test for the 2026-09-09 fix (goal session: "missing SEC/XBRL data under 500"
sweep, "are our scans catching everything they should" follow-up):
find_continuity_gaps() (utils/external/xbrl_concept_coverage.py) had two compounding blind
spots that together made every foreign private issuer invisible to continuity checking:

1. It only ever read the "us-gaap" taxonomy dict, never "ifrs-full" - a pure IFRS filer with
   zero us-gaap facts (every 20-F/40-F filer that never dual-reports under us-gaap, e.g.
   CNQ/Canadian Natural Resources, TX/Ternium, CYD/China Yuchai - all real, live-confirmed via
   companyfacts JSON) always had empty own_ends for all three CORE_CONTINUITY_CONCEPTS.
2. _annual_end_dates() only accepted forms starting with "10-K" - a foreign private issuer's
   real annual report form is "20-F" or "40-F", never "10-K"-prefixed, so even a filer that DID
   have us-gaap facts (a dual reporter) would never have those facts recognized as "annual."

Fixed by (1) also reading the ifrs-full taxonomy dict (ifrs-full uses the same "Assets"/
"Liabilities" concept names as us-gaap, and "ProfitLoss" is already a registered
CONTINUITY_CONCEPT_SYNONYMS entry for "NetIncomeLoss" - live-confirmed all three IFRS filers
above tag plain ifrs-full:Assets/Liabilities/ProfitLoss), and (2) checking form membership
against the same _ANNUAL_REPORT_FORMS set (10-K/10-K-A/10-KT/10-KT-A/20-F/20-F-A/40-F/40-F-A)
sec_statements_shared.py already treats as "a real annual filing" instead of a narrower
prefix check.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from utils.external import xbrl_concept_coverage as mod


def _annual_fact(end: str, form: str, val: float = 1.0) -> dict[str, Any]:
    return {"end": end, "val": val, "accn": "0001-25-000001", "fy": int(end[:4]) + 1, "fp": "FY", "form": form}


def _write_ifrs_companyfacts(
    cache_dir: Path, cik: str, entity_name: str, form: str, facts_by_concept: dict[str, list[str]]
) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    ifrs_full = {
        concept: {"units": {"USD": [_annual_fact(end, form) for end in ends]}}
        for concept, ends in facts_by_concept.items()
    }
    payload = {"data": {"entityName": entity_name, "facts": {"ifrs-full": ifrs_full}}}
    (cache_dir / f"{cik}.json").write_text(json.dumps(payload), encoding="utf-8")


@pytest.fixture(autouse=True)
def _fake_cache_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(mod, "CONTINUITY_DISMISSED_FILE", tmp_path / "dismissed.json")
    return tmp_path / "algo-sec-edgar-cache" / "companyfacts"


class TestIfrsFpiContinuityGaps:
    def test_pure_ifrs_filer_gap_now_detected(self, _fake_cache_dir: Path) -> None:
        # A pure IFRS 40-F filer (no us-gaap facts at all) that stopped tagging Liabilities in
        # its latest annual report - before the fix, this was entirely invisible (empty
        # own_ends for every concept, since only us-gaap was ever read AND "40-F" never passed
        # the old 10-K-prefix form filter even if it had been read).
        _write_ifrs_companyfacts(
            _fake_cache_dir,
            "0001293135",
            "VERMILION ENERGY INC.",
            "40-F",
            {
                "Assets": ["2025-12-31", "2024-12-31", "2023-12-31", "2022-12-31"],
                "Liabilities": ["2024-12-31", "2023-12-31", "2022-12-31"],
                "ProfitLoss": ["2025-12-31", "2024-12-31", "2023-12-31", "2022-12-31"],
            },
        )
        gaps = mod.find_continuity_gaps(min_prior_years=3)
        assert len(gaps) == 1
        assert gaps[0]["cik"] == "0001293135"
        assert gaps[0]["concept"] == "us-gaap:Liabilities"
        assert gaps[0]["latest_expected_end"] == "2025-12-31"

    def test_pure_ifrs_filer_consistent_no_gap(self, _fake_cache_dir: Path) -> None:
        _write_ifrs_companyfacts(
            _fake_cache_dir,
            "0001017413",
            "CANADIAN NATURAL RESOURCES LIMITED",
            "40-F",
            {
                "Assets": ["2025-12-31", "2024-12-31", "2023-12-31", "2022-12-31"],
                "Liabilities": ["2025-12-31", "2024-12-31", "2023-12-31", "2022-12-31"],
                "ProfitLoss": ["2025-12-31", "2024-12-31", "2023-12-31", "2022-12-31"],
            },
        )
        assert mod.find_continuity_gaps(min_prior_years=3) == []

    def test_20f_form_recognized_as_annual(self, _fake_cache_dir: Path) -> None:
        # Same shape as the 40-F case above but using the 20-F form - both must be recognized,
        # not just 40-F specifically.
        _write_ifrs_companyfacts(
            _fake_cache_dir,
            "0001342874",
            "TERNIUM S.A.",
            "20-F",
            {
                "Assets": ["2025-12-31", "2024-12-31", "2023-12-31", "2022-12-31"],
                "Liabilities": ["2025-12-31", "2024-12-31", "2023-12-31", "2022-12-31"],
                "ProfitLoss": ["2024-12-31", "2023-12-31", "2022-12-31"],
            },
        )
        gaps = mod.find_continuity_gaps(min_prior_years=3)
        assert len(gaps) == 1
        assert gaps[0]["concept"] == "us-gaap:NetIncomeLoss"
