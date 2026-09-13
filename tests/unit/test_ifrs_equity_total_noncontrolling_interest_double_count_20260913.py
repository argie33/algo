"""Regression test for the 2026-09-13 fix: an IFRS filer that only ever tags ifrs-full:Equity
(total equity INCLUDING noncontrolling interest) - never EquityAttributableToOwnersOfParent -
had stockholders_equity holding the NCI-inclusive total while NoncontrollingInterests was ALSO
extracted separately into minority_interest, double-counting NCI in the balance-sheet identity
(assets == liabilities + stockholders_equity + noncontrolling_interest + temporary_equity).

Live-confirmed via Adecoagro S.A.'s real companyfacts JSON (AGRO, CIK 0001499505): FY2024
Liabilities($1,706,787,000) + stockholders_equity($1,408,101,000) already sums EXACTLY to
Assets($3,114,888,000) on its own - the separately-tagged NoncontrollingInterests
($38,951,000) was overshooting the identity by precisely that amount. A live DB scan found 84
symbols total matching this exact signature (residual == -noncontrolling_interest).
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


class TestIfrsEquityTotalNoncontrollingInterestDoubleCount:
    def test_equity_total_only_nets_out_noncontrolling_interest(self) -> None:
        """AGRO-shaped: only ifrs-full:Equity tagged (no EquityAttributableToOwnersOfParent) -
        stockholders_equity must end up as the parent-only figure (Equity - NCI), not the raw
        NCI-inclusive total."""
        facts = {
            "us-gaap": {},
            "ifrs-full": {
                "Assets": {"units": {"USD": [_entry(2024, 3_114_888_000.0, "2025-03-01")]}},
                "Liabilities": {"units": {"USD": [_entry(2024, 1_706_787_000.0, "2025-03-01")]}},
                "Equity": {"units": {"USD": [_entry(2024, 1_447_052_000.0, "2025-03-01")]}},
                "NoncontrollingInterests": {"units": {"USD": [_entry(2024, 38_951_000.0, "2025-03-01")]}},
            },
        }
        rows = get_balance_sheet(_FakeClient(facts), "AGRO", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}
        assert by_year[2024]["stockholders_equity"] == 1_408_101_000.0
        assert by_year[2024]["minority_interest"] == 38_951_000.0

    def test_parent_only_concept_present_is_left_untouched(self) -> None:
        """When EquityAttributableToOwnersOfParent IS tagged for the period, it already wins
        via the existing last-listed-wins order - this fix must not double-subtract NCI from
        an already-correct parent-only value."""
        facts = {
            "us-gaap": {},
            "ifrs-full": {
                "Assets": {"units": {"USD": [_entry(2026, 89_022_000_000.0, "2027-02-01")]}},
                "Liabilities": {"units": {"USD": [_entry(2026, 0.0, "2027-02-01")]}},
                "Equity": {"units": {"USD": [_entry(2026, 89_022_000_000.0, "2027-02-01")]}},
                "EquityAttributableToOwnersOfParent": {
                    "units": {"USD": [_entry(2026, 87_588_000_000.0, "2027-02-01")]}
                },
                "NoncontrollingInterests": {"units": {"USD": [_entry(2026, 1_434_000_000.0, "2027-02-01")]}},
            },
        }
        rows = get_balance_sheet(_FakeClient(facts), "BNS", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}
        assert by_year[2026]["stockholders_equity"] == 87_588_000_000.0
        assert by_year[2026]["minority_interest"] == 1_434_000_000.0

    def test_no_noncontrolling_interest_leaves_equity_total_unchanged(self) -> None:
        """A filer with only Equity tagged and NO NoncontrollingInterests fact at all (a
        single-entity filer with no NCI) must be left completely alone - nothing to net out."""
        facts = {
            "us-gaap": {},
            "ifrs-full": {
                "Assets": {"units": {"USD": [_entry(2024, 500_000_000.0, "2025-03-01")]}},
                "Liabilities": {"units": {"USD": [_entry(2024, 200_000_000.0, "2025-03-01")]}},
                "Equity": {"units": {"USD": [_entry(2024, 300_000_000.0, "2025-03-01")]}},
            },
        }
        rows = get_balance_sheet(_FakeClient(facts), "SOLO", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}
        assert by_year[2024]["stockholders_equity"] == 300_000_000.0
