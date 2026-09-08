"""Regression test for the 2026-09-08 XBRL coverage-scan exhaustive-triage batch:
IFRS current-portion-of-borrowings understatement fix + goodwill-impairment alias.

Live-confirmed via real companyfacts JSON (see utils/external/sec_balance_sheet.py's
LongtermBorrowings/CurrentPortionOfLongtermBorrowings/CurrentBorrowingsAndCurrentPortionOf
NoncurrentBorrowings comments): Agnico Eagle Mines (CIK 0000002809) tags LongtermBorrowings
(noncurrent-only, USD 1,052,956,000 FY2024) SEPARATELY from CurrentPortionOfLongtermBorrowings
(USD 90,000,000) - the plain "LongtermBorrowings" -> "long_term_debt" mapping alone silently
dropped the current-maturities figure. PLDT (CIK 0000078150) confirms
CurrentBorrowingsAndCurrentPortionOfNoncurrentBorrowings is the same current-side addend
(LongtermBorrowings + this concept == PLDT's own separately-tagged "Borrowings" total exactly).
"""

from typing import Any

from utils.external.sec_balance_sheet import get_balance_sheet
from utils.external.sec_income_statement import get_income_statement


class _FakeClient:
    def __init__(self, facts: dict[str, Any]) -> None:
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0000000000"

    def get_company_facts(self, cik: str) -> dict[str, Any]:
        return {"facts": self._facts}


def _entry(year: int, val: float, filed: str, form: str = "40-F") -> dict[str, Any]:
    return {"end": f"{year}-12-31", "val": val, "filed": filed, "fp": "FY", "fy": year, "form": form}


class TestIfrsCurrentPortionOfBorrowings:
    def test_current_portion_of_longterm_borrowings_added_to_noncurrent(self) -> None:
        facts = {
            "us-gaap": {},
            "ifrs-full": {
                "LongtermBorrowings": {"units": {"USD": [_entry(2024, 1_052_956_000.0, "2025-02-27")]}},
                "CurrentPortionOfLongtermBorrowings": {"units": {"USD": [_entry(2024, 90_000_000.0, "2025-02-27")]}},
            },
        }
        rows = get_balance_sheet(_FakeClient(facts), "AEM", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}
        assert by_year[2024]["long_term_debt"] == 1_142_956_000.0

    def test_current_borrowings_and_current_portion_combined_added_to_noncurrent(self) -> None:
        facts = {
            "us-gaap": {},
            "ifrs-full": {
                "LongtermBorrowings": {"units": {"USD": [_entry(2024, 258_246_000_000.0, "2025-03-13", form="20-F")]}},
                "CurrentBorrowingsAndCurrentPortionOfNoncurrentBorrowings": {
                    "units": {"USD": [_entry(2024, 23_340_000_000.0, "2025-03-13", form="20-F")]}
                },
            },
        }
        rows = get_balance_sheet(_FakeClient(facts), "PLDT", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}
        assert by_year[2024]["long_term_debt"] == 281_586_000_000.0

    def test_longterm_borrowings_without_current_portion_unaffected(self) -> None:
        facts = {
            "us-gaap": {},
            "ifrs-full": {
                "LongtermBorrowings": {"units": {"USD": [_entry(2024, 1_052_956_000.0, "2025-02-27")]}},
            },
        }
        rows = get_balance_sheet(_FakeClient(facts), "AEM", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}
        assert by_year[2024]["long_term_debt"] == 1_052_956_000.0

    def test_borrowings_combined_total_not_double_counted_with_current_portion(self) -> None:
        # A filer tagging the combined "Borrowings" total directly must not also get a
        # current-portion figure added on top of it (that would double-count).
        facts = {
            "us-gaap": {},
            "ifrs-full": {
                "Borrowings": {"units": {"USD": [_entry(2025, 26_038_000_000.0, "2026-02-20")]}},
                "CurrentPortionOfLongtermBorrowings": {"units": {"USD": [_entry(2025, 500_000_000.0, "2026-02-20")]}},
            },
        }
        rows = get_balance_sheet(_FakeClient(facts), "UL", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}
        assert by_year[2025]["long_term_debt"] == 26_038_000_000.0


class TestIfrsGoodwillImpairmentAlias:
    def test_impairment_loss_recognised_goodwill_maps_to_goodwill_impairment_loss(self) -> None:
        facts = {
            "us-gaap": {},
            "ifrs-full": {
                "ImpairmentLossRecognisedInProfitOrLossGoodwill": {
                    "units": {"USD": [_entry(2025, 45_000_000.0, "2026-02-13")]}
                },
            },
        }
        rows = get_income_statement(_FakeClient(facts), "AEM", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}
        assert by_year[2025]["goodwill_impairment_loss"] == 45_000_000.0

    def test_us_gaap_goodwill_impairment_loss_not_overwritten_by_ifrs_alias(self) -> None:
        facts = {
            "us-gaap": {
                "GoodwillImpairmentLoss": {"units": {"USD": [_entry(2025, 10_000_000.0, "2026-02-13", form="10-K")]}},
            },
            "ifrs-full": {
                "ImpairmentLossRecognisedInProfitOrLossGoodwill": {
                    "units": {"USD": [_entry(2025, 999_999_999.0, "2026-02-13")]}
                },
            },
        }
        rows = get_income_statement(_FakeClient(facts), "AEM", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}
        assert by_year[2025]["goodwill_impairment_loss"] == 10_000_000.0
