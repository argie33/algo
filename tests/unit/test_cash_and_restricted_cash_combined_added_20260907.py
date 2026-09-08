"""Regression test for the 2026-09-07 fix (goal session: tie-out check_cashflow_reconciliation
restricted-cash gap rootcaused, migration 1267): ADP holds large restricted cash (funds held for
clients), so its real cash-flow statement reconciles OCF+ICF+FCF to the COMBINED cash+restricted
total (us-gaap:CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents), not to
unrestricted cash_and_equivalents alone - see migration 1267's own header for the full evidence.

Live-confirmed via real companyfacts JSON: ADP FY2026 (period end 2026-06-30) combined total =
$5,570,600,000 change from FY2025 (via the *PeriodIncreaseDecrease... concept), matching
OCF+ICF+FCF ($5.608B) almost exactly - unlike the $0.882B change in unrestricted cash alone.
"""

from typing import Any

from loaders.load_financial_statements import _BALANCE_FIELD_MAPPING
from utils.external.sec_balance_sheet import get_balance_sheet


class _FakeClient:
    def __init__(self, facts: dict[str, Any]) -> None:
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0000000000"

    def get_company_facts(self, cik: str) -> dict[str, Any]:
        return {"facts": self._facts}


def _entry(end: str, val: float, filed: str, form: str = "10-K") -> dict[str, Any]:
    year = int(end[:4])
    return {"end": end, "val": val, "filed": filed, "fp": "FY", "fy": year, "form": form}


class TestCashAndRestrictedCashCombinedWired:
    def test_field_mapping_is_identity(self) -> None:
        assert _BALANCE_FIELD_MAPPING["cash_and_restricted_cash_combined"] == "cash_and_restricted_cash_combined"

    def test_adp_style_combined_cash_maps_through_get_balance_sheet(self) -> None:
        facts = {
            "us-gaap": {
                "CashAndCashEquivalentsAtCarryingValue": {
                    "units": {"USD": [_entry("2026-06-30", 4_230_100_000.0, "2026-08-05")]}
                },
                "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents": {
                    "units": {"USD": [_entry("2026-06-30", 9_800_700_000.0, "2026-08-05")]}
                },
            },
            "ifrs-full": {},
        }
        rows = get_balance_sheet(_FakeClient(facts), "ADP", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}
        assert by_year[2026]["cash_and_restricted_cash_combined"] == 9_800_700_000.0
        # Unrestricted cash_and_equivalents still resolves to the plain concept, unchanged.
        assert by_year[2026]["cash_and_cash_equivalents_at_carrying_value"] == 4_230_100_000.0

    def test_no_restricted_cash_leaves_column_absent(self) -> None:
        facts = {
            "us-gaap": {
                "CashAndCashEquivalentsAtCarryingValue": {
                    "units": {"USD": [_entry("2026-12-31", 100_000_000.0, "2027-02-01")]}
                },
            },
            "ifrs-full": {},
        }
        rows = get_balance_sheet(_FakeClient(facts), "PLAINCO", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}
        assert "cash_and_restricted_cash_combined" not in by_year[2026]
