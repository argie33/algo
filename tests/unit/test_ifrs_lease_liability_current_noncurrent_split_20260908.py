"""Regression test for the 2026-09-08 IFRS "CurrentLeaseLiabilities"/"NoncurrentLeaseLiabilities"
fallback (goal session: XBRL coverage-scan backlog triage, 3rd batch this session).

Live-confirmed via Agnico Eagle's real companyfacts JSON (CIK 0000002809) that the combined
"LeaseLiabilities" concept (already aliased to operating_lease_liability) exactly equals
CurrentLeaseLiabilities + NoncurrentLeaseLiabilities for FY2023-2025 (FY2025:
USD 125,199,000 == USD 30,480,000 + USD 94,719,000). A scan of the full on-disk companyfacts
cache found 38 real filers - POSCO Holdings (CIK 0000889132) among them - that tag ONLY the
split pair and never the combined concept at all: FY2024 CurrentLeaseLiabilities=
KRW 161,601,000,000 + NoncurrentLeaseLiabilities=KRW 744,500,000,000, zero "LeaseLiabilities"
fact for any fiscal year.
"""

from typing import Any

from utils.external.sec_balance_sheet import (
    _fill_operating_lease_liability_from_current_noncurrent_split,
    get_balance_sheet,
)


class _FakeClient:
    def __init__(self, facts: dict[str, Any]) -> None:
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0000000000"

    def get_company_facts(self, cik: str) -> dict[str, Any]:
        return {"facts": self._facts}


def _entry(year: int, val: float, filed: str, form: str = "20-F") -> dict[str, Any]:
    return {"end": f"{year}-12-31", "val": val, "filed": filed, "fp": "FY", "fy": year, "form": form}


class TestIfrsLeaseLiabilitySplitFallback:
    def test_split_summed_when_combined_concept_absent(self) -> None:
        # POSCO Holdings shape (real values, real ratio KRW 161,601,000,000/744,500,000,000 -
        # kept as the ratio, expressed in USD here so the assertion doesn't depend on this
        # loader's separate FX-conversion pipeline): only the split pair, no combined
        # "LeaseLiabilities" fact.
        facts = {
            "us-gaap": {},
            "ifrs-full": {
                "CurrentLeaseLiabilities": {"units": {"USD": [_entry(2024, 161_601_000.0, "2025-04-30")]}},
                "NoncurrentLeaseLiabilities": {"units": {"USD": [_entry(2024, 744_500_000.0, "2025-04-30")]}},
            },
        }
        rows = get_balance_sheet(_FakeClient(facts), "PKX", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}
        assert by_year[2024]["operating_lease_liability"] == 906_101_000.0

    def test_combined_concept_wins_over_split_when_both_present(self) -> None:
        # Agnico Eagle shape: both the combined tag and the split tagged for the same year -
        # the combined figure (this aggregation's own primary/authoritative source) must win,
        # not the split sum, even though the two happen to agree for AEM specifically.
        facts = {
            "us-gaap": {},
            "ifrs-full": {
                "LeaseLiabilities": {"units": {"USD": [_entry(2025, 125_199_000.0, "2026-02-13")]}},
                "CurrentLeaseLiabilities": {"units": {"USD": [_entry(2025, 30_480_000.0, "2026-02-13")]}},
                "NoncurrentLeaseLiabilities": {"units": {"USD": [_entry(2025, 94_719_000.0, "2026-02-13")]}},
            },
        }
        rows = get_balance_sheet(_FakeClient(facts), "AEM", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}
        assert by_year[2025]["operating_lease_liability"] == 125_199_000.0

    def test_requires_both_halves_present(self) -> None:
        rows: list[dict[str, Any]] = [
            {
                "symbol": "XYZ",
                "fiscal_year": 2025,
                "current_lease_liabilities": 5_000_000.0,
            }
        ]
        _fill_operating_lease_liability_from_current_noncurrent_split(rows)
        assert rows[0].get("operating_lease_liability") is None
        assert "current_lease_liabilities" not in rows[0]

    def test_never_overwrites_a_real_value(self) -> None:
        rows: list[dict[str, Any]] = [
            {
                "symbol": "AEM",
                "fiscal_year": 2025,
                "operating_lease_liability": 125_199_000.0,
                "current_lease_liabilities": 1.0,
                "noncurrent_lease_liabilities": 1.0,
            }
        ]
        _fill_operating_lease_liability_from_current_noncurrent_split(rows)
        assert rows[0]["operating_lease_liability"] == 125_199_000.0
