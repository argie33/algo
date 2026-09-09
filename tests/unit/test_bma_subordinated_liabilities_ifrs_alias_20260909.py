"""Regression test for the 2026-09-09 IFRS "SubordinatedLiabilities" alias (goal session:
SEC/XBRL missing-data reduction, total_debt_not_itemized investigation continuation).

BMA (Banco Macro, an Argentine bank ADR filing 20-F) tags NEITHER "Borrowings" NOR
"DebtSecurities" NOR any LongtermBorrowings/ShorttermBorrowings concept - live-confirmed via
its real companyfacts JSON (CIK 0001347426) that its only debt-instrument-shaped liability
concept is "SubordinatedLiabilities": continuous, material, real values every fiscal year
2018-2024 (e.g. FY2024 period end 2024-12-31 = ARS 417,675,451,000, ~4% of that year's total
Liabilities of ARS 10,441,712,229,000 - a plausible subordinated-notes tranche scale for a
bank). Same semantic class as the existing us-gaap "SubordinatedDebt"/"JuniorSubordinatedDebenture
OwedToUnconsolidatedSubsidiaryTrust" fallback (IBOC/HBT trust-preferred securities) - this is
IFRS's equivalent concept name for the same real instrument type.
"""

from typing import Any

from utils.external.sec_balance_sheet import get_balance_sheet


class _FakeClient:
    def __init__(self, facts: dict[str, Any]) -> None:
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0001347426"

    def get_company_facts(self, cik: str) -> dict[str, Any]:
        return {"facts": self._facts}


def _entry(year: int, val: float, filed: str, form: str = "20-F") -> dict[str, Any]:
    return {"end": f"{year}-12-31", "val": val, "filed": filed, "fp": "FY", "fy": year, "form": form}


class TestIfrsSubordinatedLiabilitiesAlias:
    def test_subordinated_liabilities_maps_to_long_term_debt(self) -> None:
        facts = {
            "us-gaap": {},
            "ifrs-full": {
                "SubordinatedLiabilities": {"units": {"USD": [_entry(2024, 417_675_451_000.0, "2025-04-21")]}},
            },
        }
        rows = get_balance_sheet(_FakeClient(facts), "BMA", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}
        assert by_year[2024]["long_term_debt"] == 417_675_451_000.0

    def test_borrowings_wins_over_subordinated_liabilities_fallback(self) -> None:
        # A filer reporting the more common "Borrowings" concept keeps that value -
        # SubordinatedLiabilities never overwrites it (listed last, same last-listed-wins
        # convention as DebtSecurities/Borrowings themselves).
        facts = {
            "us-gaap": {},
            "ifrs-full": {
                "Borrowings": {"units": {"USD": [_entry(2025, 5_000_000_000.0, "2026-02-20")]}},
                "SubordinatedLiabilities": {"units": {"USD": [_entry(2025, 999_999_999.0, "2026-02-20")]}},
            },
        }
        rows = get_balance_sheet(_FakeClient(facts), "MIXED", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}
        assert by_year[2025]["long_term_debt"] == 5_000_000_000.0
