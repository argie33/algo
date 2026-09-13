"""Regression test for the 2026-09-13 fix: GAAP sibling of the IFRS Equity-total
noncontrolling-interest double-count bug (see
test_ifrs_equity_total_noncontrolling_interest_double_count_20260913.py). A filer that never
tags a parent-only equity concept ("StockholdersEquity"/"PartnersCapital"/"MembersEquity") -
only the "...IncludingPortionAttributableToNoncontrollingInterest" fallback - had
stockholders_equity holding the NCI-inclusive total while MinorityInterest was ALSO extracted
separately, double-counting NCI in the balance-sheet identity.

Live-confirmed via Teekay Corp's real companyfacts JSON (TK, CIK 0000911971): FY2023 has ZERO
StockholdersEquity facts ever, only StockholdersEquityIncludingPortionAttributableTo
NoncontrollingInterest ($1,800,346,000) and MinorityInterest ($1,068,068,000). True parent-only
equity = 1,800,346,000 - 1,068,068,000 = 732,278,000. Real, directly-tagged Liabilities
($396,292,000) is NOT itself wrong - a numeric coincidence with the unrelated
assets-minus-equity derivation fallback initially looked like the same bug shape before being
ruled out (see scripts/fix_balance_sheet_nci_double_count.py's docstring).
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


class TestGaapEquityTotalNoncontrollingInterestDoubleCount:
    def test_stockholders_equity_including_nci_only_nets_out_minority_interest(self) -> None:
        facts = {
            "us-gaap": {
                "Assets": {"units": {"USD": [_entry(2023, 2_196_638_000.0, "2024-03-01")]}},
                "Liabilities": {"units": {"USD": [_entry(2023, 396_292_000.0, "2024-03-01")]}},
                "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest": {
                    "units": {"USD": [_entry(2023, 1_800_346_000.0, "2024-03-01")]}
                },
                "MinorityInterest": {"units": {"USD": [_entry(2023, 1_068_068_000.0, "2024-03-01")]}},
            },
            "ifrs-full": {},
        }
        rows = get_balance_sheet(_FakeClient(facts), "TK", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}
        assert by_year[2023]["stockholders_equity"] == 732_278_000.0
        assert by_year[2023]["minority_interest"] == 1_068_068_000.0
        # Liabilities is real and directly tagged - must be left completely untouched.
        assert by_year[2023]["liabilities"] == 396_292_000.0

    def test_real_stockholders_equity_present_is_left_untouched(self) -> None:
        facts = {
            "us-gaap": {
                "Assets": {"units": {"USD": [_entry(2025, 1000.0, "2026-03-01")]}},
                "Liabilities": {"units": {"USD": [_entry(2025, 400.0, "2026-03-01")]}},
                "StockholdersEquity": {"units": {"USD": [_entry(2025, 500.0, "2026-03-01")]}},
                "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest": {
                    "units": {"USD": [_entry(2025, 600.0, "2026-03-01")]}
                },
                "MinorityInterest": {"units": {"USD": [_entry(2025, 100.0, "2026-03-01")]}},
            },
            "ifrs-full": {},
        }
        rows = get_balance_sheet(_FakeClient(facts), "NORMALCO", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}
        assert by_year[2025]["stockholders_equity"] == 500.0

    def test_partners_capital_including_nci_family_also_covered(self) -> None:
        facts = {
            "us-gaap": {
                "Assets": {"units": {"USD": [_entry(2024, 5000.0, "2025-03-01")]}},
                "Liabilities": {"units": {"USD": [_entry(2024, 3000.0, "2025-03-01")]}},
                "PartnersCapitalIncludingPortionAttributableToNoncontrollingInterest": {
                    "units": {"USD": [_entry(2024, 2000.0, "2025-03-01")]}
                },
                "MinorityInterest": {"units": {"USD": [_entry(2024, 200.0, "2025-03-01")]}},
            },
            "ifrs-full": {},
        }
        rows = get_balance_sheet(_FakeClient(facts), "LPCO", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}
        assert by_year[2024]["stockholders_equity"] == 1800.0

    def test_no_minority_interest_leaves_equity_total_unchanged(self) -> None:
        """No MinorityInterest tagged at all (a filer with genuinely no NCI) - nothing to net
        out. The "...IncludingPortion..." fallback key is left exactly as fetched; it collapses
        onto the stockholders_equity DB column later via financial_statements_balance_config.py's
        fallback-only field mapping (outside this module's own scope), not touched here."""
        facts = {
            "us-gaap": {
                "Assets": {"units": {"USD": [_entry(2024, 1000.0, "2025-03-01")]}},
                "Liabilities": {"units": {"USD": [_entry(2024, 700.0, "2025-03-01")]}},
                "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest": {
                    "units": {"USD": [_entry(2024, 300.0, "2025-03-01")]}
                },
            },
            "ifrs-full": {},
        }
        rows = get_balance_sheet(_FakeClient(facts), "SOLOGAAP", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}
        assert "stockholders_equity" not in by_year[2024]
        assert by_year[2024]["stockholders_equity_including_portion_attributable_to_noncontrolling_interest"] == 300.0
