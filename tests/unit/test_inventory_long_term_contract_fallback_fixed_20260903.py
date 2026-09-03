"""Regression test for the 2026-09-03 fix (goal session: "missing SEC/XBRL data under 6k"
sweep, inventory gap investigation): long-term-contract manufacturers (aerospace/defense
primes) tag real inventory under "InventoryNetOfAllowancesCustomerAdvancesAndProgressBillings"
instead of the plain "InventoryNet" concept.

Live-confirmed via real companyfacts JSON:
- BA (Boeing): zero facts ever under "InventoryNet" despite a real, huge inventory balance
  ($78,823,000,000 FY2021 through $84,679,000,000 FY2025, continuous) tagged only under the
  fallback concept.
- HII (Huntington Ingalls): both concepts defined in its taxonomy, but "InventoryNet" itself
  has zero actual facts filed - real values ($183,000,000-$219,000,000 FY2022-2025) are all
  under the fallback concept, confirming it's a real, reused standard element for this filer
  shape rather than a Boeing-specific one-off.
"""

from typing import Any

from loaders.helpers.sec_base import SecEdgarStatementLoader
from loaders.load_financial_statements import _BALANCE_FIELD_MAPPING, _DEBT_FALLBACK_ONLY_FIELDS
from utils.external.sec_statements import get_balance_sheet


class _FakeClient:
    def __init__(self, facts: dict[str, Any]) -> None:
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0000000000"

    def get_company_facts(self, cik: str) -> dict[str, Any]:
        return {"facts": self._facts}


def _entry(year: int, val: float, filed: str, form: str = "10-K") -> dict[str, Any]:
    return {"end": f"{year}-12-31", "val": val, "filed": filed, "fp": "FY", "fy": year, "form": form}


class TestInventoryLongTermContractFallbackFixed:
    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_balance_sheet"
        loader.period = "annual"
        loader.statement_type = "balance"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "inventory", "data_unavailable", "reason"})
        loader._field_mapping = {
            "inventory": "inventory",
            "inventory_net": "inventory",
            "inventory_net_of_allowances_customer_advances_and_progress_billings": "inventory",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset(
            {"inventory_net_of_allowances_customer_advances_and_progress_billings"}
        )
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        return loader

    def test_field_mapping_wires_fallback_concept(self) -> None:
        assert (
            _BALANCE_FIELD_MAPPING["inventory_net_of_allowances_customer_advances_and_progress_billings"] == "inventory"
        )
        assert "inventory_net_of_allowances_customer_advances_and_progress_billings" in _DEBT_FALLBACK_ONLY_FIELDS

    def test_boeing_style_inventory_recovered(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "BA",
            "fiscal_year": 2025,
            "inventory_net_of_allowances_customer_advances_and_progress_billings": 84_679_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["inventory"] == 84_679_000_000.0

    def test_never_overwrites_a_real_inventory_value(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "SOME_FILER",
            "fiscal_year": 2025,
            "inventory_net": 500_000_000.0,
            "inventory_net_of_allowances_customer_advances_and_progress_billings": 1.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["inventory"] == 500_000_000.0

    def test_boeing_style_maps_through_get_balance_sheet(self) -> None:
        facts = {
            "us-gaap": {
                "InventoryNetOfAllowancesCustomerAdvancesAndProgressBillings": {
                    "units": {"USD": [_entry(2025, 84_679_000_000.0, "2026-01-28")]}
                },
            },
        }
        rows = get_balance_sheet(_FakeClient(facts), "BA", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}
        assert by_year[2025]["inventory_net_of_allowances_customer_advances_and_progress_billings"] == 84_679_000_000.0
