"""Regression test for a coverage gap in get_cash_flow()'s IFRS aliases
(utils/external/sec_statements.py):

Migration 1206 added two new us-gaap-only concepts (ShareBasedCompensation,
PaymentsForRepurchaseOfCommonStock) with no IFRS equivalents, so every IFRS-only filer
(20-F/40-F, e.g. WPM/Wheaton Precious Metals, TS/Tenaris, E/Eni) got NULL for both -
the same "foreign filer silently dropped" bug class every other alias in
_CASHFLOW_IFRS_ALIASES already guards against.

Live-confirmed via real companyfacts JSON (not guessed):
- "AdjustmentsForSharebasedPayments" is WPM's real cash-flow-statement non-cash SBC
  addback: $16.57M FY2024, $26.03M FY2025.
- "PurchaseOfTreasuryShares" is TS's/E's real financing-activities buyback outflow:
  TS $1.44B FY2024/$1.36B FY2025, E EUR2.00B FY2024/EUR1.88B FY2025.

The buyback alias's target_key must be "payments_for_repurchase_of_common_stock" (the
field_mapping dict *key*, matching the us-gaap concept's snake_cased name), not
"common_stock_repurchased" (the DB column name field_mapping maps it *to*) - using the
DB column name directly would make sec_field not in field_mapping, silently dropping the
value with an "unmapped field" warning instead of writing it.
"""

from typing import Any

from utils.external.sec_statements import get_cash_flow


class _FakeClient:
    def __init__(self, facts: dict[str, Any]) -> None:
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0000000000"

    def get_company_facts(self, cik: str) -> dict[str, Any]:
        return {"facts": self._facts}


def _concept(entries: list[dict[str, Any]]) -> dict[str, Any]:
    return {"units": {"USD": entries}}


def _entry(year: int, val: float, filed: str, form: str = "20-F") -> dict[str, Any]:
    return {
        "start": f"{year}-01-01",
        "end": f"{year}-12-31",
        "val": val,
        "filed": filed,
        "fp": "FY",
        "fy": year,
        "form": form,
    }


class TestIfrsShareBasedCompensationAlias:
    def test_adjustments_for_sharebased_payments_maps_to_stock_based_compensation(self) -> None:
        facts = {
            "us-gaap": {},
            "ifrs-full": {
                "AdjustmentsForSharebasedPayments": _concept([_entry(2025, 26_029_000.0, "2026-03-31", form="40-F")]),
            },
        }
        client = _FakeClient(facts)

        rows = get_cash_flow(client, "WPM", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        assert by_year[2025]["share_based_compensation"] == 26_029_000.0


class TestIfrsBuybackAlias:
    def test_purchase_of_treasury_shares_maps_to_repurchase_field_mapping_key(self) -> None:
        facts = {
            "us-gaap": {},
            "ifrs-full": {
                "PurchaseOfTreasuryShares": _concept([_entry(2024, 1_441_843_000.0, "2026-03-31")]),
            },
        }
        client = _FakeClient(facts)

        rows = get_cash_flow(client, "TS", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}

        # target_key is the field_mapping *key*, not the "common_stock_repurchased" DB
        # column it ultimately maps to - get_cash_flow()'s raw row dict still uses the
        # pre-mapping key.
        assert by_year[2024]["payments_for_repurchase_of_common_stock"] == 1_441_843_000.0
