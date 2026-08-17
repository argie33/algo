"""Regression test for the 2026-08-17 IFRS short-term-borrowings alias (loader-review
goal continuation).

"ShorttermBorrowings" is IFRS's paired current-portion concept to "LongtermBorrowings"
(already aliased to long_term_debt) - same convention as us-gaap's CommercialPaper/
ShortTermBorrowings, both of which already map to the short_term_debt column via
_BALANCE_FIELD_MAPPING as genuine either/or alternatives (not fallback-only). No IFRS
alias existed for it, so every IFRS-only filer (20-F/40-F) got NULL short_term_debt from
this concept entirely, understating total_debt for filers that carry real short-term
borrowings.

Live-confirmed via real companyfacts JSON that "ShorttermBorrowings" is reported in USD
by large, well-known IFRS filers - TSM (Taiwan Semiconductor) FY2021: $4,142,800,000
(filed 2022-04-14) - plus Novartis, Rio Tinto, TotalEnergies, ArcelorMittal, Petrobras,
and 40+ others confirmed present in SEC's frames API for CY2020Q4I. Some IFRS filers
(ASR, E/Eni, AEG/Aegon) report this concept only in local currency (MXN/EUR) with no USD
fact - those correctly get NULL via the pre-existing non-USD currency guard, same as
every other balance-sheet field.
"""

from typing import Any

from utils.external.sec_statements import get_balance_sheet


class _FakeClient:
    def __init__(self, facts: dict[str, Any]) -> None:
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0000000000"

    def get_company_facts(self, cik: str) -> dict[str, Any]:
        return {"facts": self._facts}


def _entry(year: int, val: float, filed: str, form: str = "20-F") -> dict[str, Any]:
    return {"end": f"{year}-12-31", "val": val, "filed": filed, "fp": "FY", "fy": year, "form": form}


class TestIfrsShortTermBorrowingsAlias:
    def test_shortterm_borrowings_maps_to_short_term_debt(self) -> None:
        facts = {
            "us-gaap": {},
            "ifrs-full": {
                "ShorttermBorrowings": {"units": {"USD": [_entry(2021, 4_142_800_000.0, "2022-04-14")]}},
            },
        }
        client = _FakeClient(facts)

        rows = get_balance_sheet(client, "TSM", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        # target_key is "short_term_borrowings" (the field_mapping dict *key*, matching
        # the us-gaap ShortTermBorrowings concept's snake_cased name), not "short_term_debt"
        # (the DB column it maps to) - using the column name directly would make
        # sec_field not in field_mapping, silently dropping the value.
        assert by_year[2021]["short_term_borrowings"] == 4_142_800_000.0

    def test_non_usd_shortterm_borrowings_rejected_by_currency_guard(self) -> None:
        # ASR reports this concept only in MXN, with no USD fact - must not fabricate a
        # USD figure from the raw MXN magnitude (same guard as the lease-liability and
        # generic non-USD tests).
        facts = {
            "us-gaap": {},
            "ifrs-full": {
                "ShorttermBorrowings": {"units": {"MXN": [_entry(2024, 500_000_000.0, "2025-04-01")]}},
            },
        }
        client = _FakeClient(facts)

        rows = get_balance_sheet(client, "ASR", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert 2024 not in by_year or "short_term_borrowings" not in by_year[2024]
