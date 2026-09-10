"""Regression test for the 2026-09-08 XBRL coverage-scan exhaustiveness fix:
cash_and_restricted_cash_combined fallback-summing from split RestrictedCash concepts.

Found via the exhaustiveness audit (goal session): a bare "RestrictedCash" noise substring in
utils/external/xbrl_concept_coverage.py's NOISE_SUBSTRINGS was silently swallowing
us-gaap:RestrictedCash/RestrictedCashCurrent (1,488/1,165 filers) - a real, material balance
without ever being individually reviewed. Live-confirmed via Eastman Kodak's real companyfacts
JSON (CIK 0000031235): FY2025 CashAndCashEquivalentsAtCarryingValue = $337,000,000 +
RestrictedCashCurrent = $9,000,000, zero combined
"CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents" fact ever filed.
"""

from typing import Any

from utils.external.sec_balance_sheet import get_balance_sheet


class _FakeClient:
    def __init__(self, facts: dict[str, Any]) -> None:
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0000031235"

    def get_company_facts(self, cik: str) -> dict[str, Any]:
        return {"facts": self._facts}


def _entry(year: int, val: float, filed: str, form: str = "10-K") -> dict[str, Any]:
    return {"end": f"{year}-12-31", "val": val, "filed": filed, "fp": "FY", "fy": year, "form": form}


class TestRestrictedCashCombinedFallback:
    def test_current_restricted_cash_added_to_unrestricted_cash(self) -> None:
        facts = {
            "us-gaap": {
                "CashAndCashEquivalentsAtCarryingValue": {
                    "units": {"USD": [_entry(2025, 337_000_000.0, "2026-02-20")]}
                },
                "RestrictedCashCurrent": {"units": {"USD": [_entry(2025, 9_000_000.0, "2026-02-20")]}},
            },
        }
        rows = get_balance_sheet(_FakeClient(facts), "KODK", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}
        assert by_year[2025]["cash_and_restricted_cash_combined"] == 346_000_000.0

    def test_bare_restricted_cash_and_cash_equivalents_alias_used_when_no_split_tagged(self) -> None:
        facts = {
            "us-gaap": {
                "CashAndCashEquivalentsAtCarryingValue": {
                    "units": {"USD": [_entry(2011, 2_800_000_000.0, "2012-11-01")]}
                },
                "RestrictedCashAndCashEquivalents": {"units": {"USD": [_entry(2011, 77_200_000.0, "2012-11-01")]}},
            },
        }
        rows = get_balance_sheet(_FakeClient(facts), "APD", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}
        assert by_year[2011]["cash_and_restricted_cash_combined"] == 2_877_200_000.0

    def test_does_not_overwrite_real_combined_tag(self) -> None:
        facts = {
            "us-gaap": {
                "CashAndCashEquivalentsAtCarryingValue": {
                    "units": {"USD": [_entry(2025, 100_000_000.0, "2026-02-20")]}
                },
                "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents": {
                    "units": {"USD": [_entry(2025, 150_000_000.0, "2026-02-20")]}
                },
                "RestrictedCashCurrent": {"units": {"USD": [_entry(2025, 9_000_000.0, "2026-02-20")]}},
            },
        }
        rows = get_balance_sheet(_FakeClient(facts), "TEST", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}
        assert by_year[2025]["cash_and_restricted_cash_combined"] == 150_000_000.0
