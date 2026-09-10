"""Regression test for the 2026-09-08 IFRS "Borrowings"/"NoncontrollingInterests" aliases
(goal session: scores-reload due-diligence audit, IFRS coverage-scan follow-up).

"Borrowings" is IFRS's single COMBINED debt concept for filers that don't split current/
noncurrent debt the way "LongtermBorrowings"/"ShorttermBorrowings" assume - live-confirmed via
Unilever PLC's real companyfacts JSON (CIK 0000217410): FY2025 Borrowings=EUR 26,038,000,000,
with no LongtermBorrowings/ShorttermBorrowings/CurrentBorrowings/NoncurrentBorrowings concept
tagged at all.

"NoncontrollingInterests" is IFRS's direct equivalent of us-gaap's "MinorityInterest" - live-
confirmed via Bank of Nova Scotia's real companyfacts JSON (CIK 0000009631): FY2026 Q1
NoncontrollingInterests=CAD 1,434,000,000, and EquityAttributableToOwnersOfParent (CAD
87,588,000,000) + NoncontrollingInterests exactly equals the filer's own total Equity fact
(CAD 89,022,000,000).
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


def _entry(year: int, val: float, filed: str, form: str = "20-F") -> dict[str, Any]:
    return {"end": f"{year}-12-31", "val": val, "filed": filed, "fp": "FY", "fy": year, "form": form}


class TestIfrsBorrowingsAlias:
    def test_borrowings_maps_to_long_term_debt(self) -> None:
        facts = {
            "us-gaap": {},
            "ifrs-full": {
                "Borrowings": {"units": {"USD": [_entry(2025, 26_038_000_000.0, "2026-02-20")]}},
            },
        }
        rows = get_balance_sheet(_FakeClient(facts), "UL", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}
        assert by_year[2025]["long_term_debt"] == 26_038_000_000.0

    def test_split_concepts_win_over_borrowings_fallback(self) -> None:
        # A filer reporting the precise split keeps that value - Borrowings never overwrites it.
        facts = {
            "us-gaap": {},
            "ifrs-full": {
                "Borrowings": {"units": {"USD": [_entry(2025, 999_999_999.0, "2026-02-20")]}},
                "LongtermBorrowings": {"units": {"USD": [_entry(2025, 5_000_000_000.0, "2026-02-20")]}},
            },
        }
        rows = get_balance_sheet(_FakeClient(facts), "SPLIT", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}
        assert by_year[2025]["long_term_debt"] == 5_000_000_000.0


class TestIfrsNoncontrollingInterestsAlias:
    def test_noncontrolling_interests_maps_to_minority_interest(self) -> None:
        facts = {
            "us-gaap": {},
            "ifrs-full": {
                "NoncontrollingInterests": {"units": {"USD": [_entry(2026, 1_434_000_000.0, "2026-03-01")]}},
            },
        }
        rows = get_balance_sheet(_FakeClient(facts), "BNS", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}
        assert by_year[2026]["minority_interest"] == 1_434_000_000.0
