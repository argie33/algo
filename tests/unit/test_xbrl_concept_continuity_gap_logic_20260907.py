"""Regression tests for find_continuity_gaps() (utils/external/xbrl_concept_coverage.py).

Added 2026-09-07 (goal session continuation: "what about when companies change things - is
that covered?"). xbrl_new_concepts.py/find_gaps() only catches a concept appearing for the
FIRST time anywhere in the universe. This is the mirror-image case: a specific filer that
tagged a core concept every year for years suddenly stops - either a taxonomy/tag migration
(the filer's XBRL agent switched to a renamed/synonym concept) or a real extraction gap.

Builds real companyfacts-JSON-shaped fixtures (same 'end'/'val'/'form' fact shape confirmed
live against the on-disk SEC EDGAR cache) under a faked cache directory, same convention as
tests/unit/test_file_lock_dead_owner_pid_not_waited_out_20260907.py's tempfile.gettempdir patch.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from utils.external import xbrl_concept_coverage as mod


def _annual_fact(end: str, val: float = 1.0) -> dict[str, Any]:
    return {"end": end, "val": val, "accn": "0001-25-000001", "fy": int(end[:4]) + 1, "fp": "FY", "form": "10-K"}


def _write_companyfacts(cache_dir: Path, cik: str, entity_name: str, facts_by_concept: dict[str, list[str]]) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    us_gaap = {
        concept: {"units": {"USD": [_annual_fact(end) for end in ends]}} for concept, ends in facts_by_concept.items()
    }
    payload = {"data": {"entityName": entity_name, "facts": {"us-gaap": us_gaap}}}
    (cache_dir / f"{cik}.json").write_text(json.dumps(payload), encoding="utf-8")


@pytest.fixture(autouse=True)
def _fake_cache_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr("tempfile.gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(mod, "CONTINUITY_DISMISSED_FILE", tmp_path / "dismissed.json")
    return tmp_path / "algo-sec-edgar-cache" / "companyfacts"


class TestFindContinuityGaps:
    def test_concept_missing_only_in_latest_year_flags(self, _fake_cache_dir: Path) -> None:
        _write_companyfacts(
            _fake_cache_dir,
            "0000000001",
            "STOPPED REPORTING NET INCOME INC",
            {
                "Assets": ["2025-12-31", "2024-12-31", "2023-12-31", "2022-12-31"],
                "Liabilities": ["2025-12-31", "2024-12-31", "2023-12-31", "2022-12-31"],
                # NetIncomeLoss present every prior year, absent in the latest (2025) year -
                # this is the taxonomy-migration/tag-change signature.
                "NetIncomeLoss": ["2024-12-31", "2023-12-31", "2022-12-31"],
            },
        )
        gaps = mod.find_continuity_gaps(min_prior_years=3)
        assert len(gaps) == 1
        assert gaps[0]["cik"] == "0000000001"
        assert gaps[0]["concept"] == "us-gaap:NetIncomeLoss"
        assert gaps[0]["latest_expected_end"] == "2025-12-31"
        assert gaps[0]["prior_years_present"] == ["2024-12-31", "2023-12-31", "2022-12-31"]

    def test_concept_present_every_year_no_gap(self, _fake_cache_dir: Path) -> None:
        _write_companyfacts(
            _fake_cache_dir,
            "0000000002",
            "CONSISTENT FILER CORP",
            {
                "Assets": ["2025-12-31", "2024-12-31", "2023-12-31", "2022-12-31"],
                "Liabilities": ["2025-12-31", "2024-12-31", "2023-12-31", "2022-12-31"],
                "NetIncomeLoss": ["2025-12-31", "2024-12-31", "2023-12-31", "2022-12-31"],
            },
        )
        assert mod.find_continuity_gaps(min_prior_years=3) == []

    def test_concept_never_tagged_at_all_is_not_a_continuity_gap(self, _fake_cache_dir: Path) -> None:
        # A REIT-style filer with genuinely no NetIncomeLoss concept ever - this is a coverage
        # gap (find_gaps()'s territory), not a continuity regression, and must not be flagged.
        _write_companyfacts(
            _fake_cache_dir,
            "0000000003",
            "NEVER HAD NET INCOME REIT",
            {
                "Assets": ["2025-12-31", "2024-12-31", "2023-12-31", "2022-12-31"],
                "Liabilities": ["2025-12-31", "2024-12-31", "2023-12-31", "2022-12-31"],
            },
        )
        assert mod.find_continuity_gaps(min_prior_years=3) == []

    def test_insufficient_history_skipped(self, _fake_cache_dir: Path) -> None:
        # Only 2 distinct fiscal years of history total - below min_prior_years=3's required
        # depth (need min_prior_years+1 distinct anchor years) - not enough to judge "used to
        # report every year," so this must be silently skipped rather than flagged.
        _write_companyfacts(
            _fake_cache_dir,
            "0000000004",
            "RECENT IPO INC",
            {
                "Assets": ["2025-12-31", "2024-12-31"],
                "Liabilities": ["2025-12-31", "2024-12-31"],
                "NetIncomeLoss": ["2024-12-31"],
            },
        )
        assert mod.find_continuity_gaps(min_prior_years=3) == []

    def test_inconsistent_prior_history_not_flagged(self, _fake_cache_dir: Path) -> None:
        # NetIncomeLoss missing in 2023 too (not just the latest year) - this was never a
        # consistent 3-year streak, so a gap in the latest year isn't a NEW regression.
        _write_companyfacts(
            _fake_cache_dir,
            "0000000005",
            "ALREADY PATCHY FILER LLC",
            {
                "Assets": ["2025-12-31", "2024-12-31", "2023-12-31", "2022-12-31"],
                "Liabilities": ["2025-12-31", "2024-12-31", "2023-12-31", "2022-12-31"],
                "NetIncomeLoss": ["2024-12-31", "2022-12-31"],
            },
        )
        assert mod.find_continuity_gaps(min_prior_years=3) == []

    def test_dismissed_filer_concept_excluded(self, _fake_cache_dir: Path) -> None:
        _write_companyfacts(
            _fake_cache_dir,
            "0000000006",
            "LEGITIMATELY WOUND DOWN INC",
            {
                "Assets": ["2025-12-31", "2024-12-31", "2023-12-31", "2022-12-31"],
                "Liabilities": ["2025-12-31", "2024-12-31", "2023-12-31", "2022-12-31"],
                "NetIncomeLoss": ["2024-12-31", "2023-12-31", "2022-12-31"],
            },
        )
        mod.save_continuity_dismissed({"0000000006:NetIncomeLoss": "final 10-K before going private"})
        assert mod.find_continuity_gaps(min_prior_years=3) == []

    def test_no_cache_returns_empty(self, _fake_cache_dir: Path) -> None:
        assert mod.find_continuity_gaps(min_prior_years=3) == []


class TestNetIncomeLossSynonymFallback:
    """ADDED 2026-09-08 (goal session: score/XBRL sanity sweep, live scan of the on-disk
    companyfacts cache via scripts/xbrl_concept_continuity_scan.py). Live-confirmed via Ford
    Motor Co (CIK 0000037996, real FY2025 10-K filed 2026-02-11) and Primerica (PRI, already
    documented in sec_income_statement.py's 2026-08-17 fix comment): the checker's original
    literal "NetIncomeLoss" tag check false-positived on every filer whose real bottom-line tag
    is "ProfitLoss" instead - 23 of 33 originally-flagged gaps in one live scan were this exact
    pattern, since our own extraction pipeline (financial_statements_income_config.py's
    _INCOME_FIELD_MAPPING) already maps both tags to the same "net_income" column, so no data
    is actually lost. CONTINUITY_CONCEPT_SYNONYMS fixes this by treating a synonym tag as
    satisfying continuity the same way the real tag would.
    """

    def test_profit_loss_synonym_satisfies_net_income_loss_continuity(self, _fake_cache_dir: Path) -> None:
        _write_companyfacts(
            _fake_cache_dir,
            "0000037996",
            "FORD MOTOR CO",
            {
                "Assets": ["2025-12-31", "2024-12-31", "2023-12-31", "2022-12-31"],
                "Liabilities": ["2025-12-31", "2024-12-31", "2023-12-31", "2022-12-31"],
                "NetIncomeLoss": ["2024-12-31", "2023-12-31", "2022-12-31"],
                # Latest year's bottom line is tagged ProfitLoss instead of NetIncomeLoss - a
                # synonym switch, not a real gap.
                "ProfitLoss": ["2025-12-31"],
            },
        )
        assert mod.find_continuity_gaps(min_prior_years=3) == []

    def test_missing_with_no_synonym_present_still_flags(self, _fake_cache_dir: Path) -> None:
        # Same shape, but nothing tags the latest year under ANY known synonym - still a real gap.
        _write_companyfacts(
            _fake_cache_dir,
            "0000037997",
            "GENUINELY STOPPED REPORTING INC",
            {
                "Assets": ["2025-12-31", "2024-12-31", "2023-12-31", "2022-12-31"],
                "Liabilities": ["2025-12-31", "2024-12-31", "2023-12-31", "2022-12-31"],
                "NetIncomeLoss": ["2024-12-31", "2023-12-31", "2022-12-31"],
            },
        )
        gaps = mod.find_continuity_gaps(min_prior_years=3)
        assert len(gaps) == 1
        assert gaps[0]["concept"] == "us-gaap:NetIncomeLoss"
