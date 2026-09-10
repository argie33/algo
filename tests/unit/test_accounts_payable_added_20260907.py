"""Regression test for the 2026-09-07 fix (goal session: XBRL concept coverage scanner
follow-up, migration 1263): "AccountsPayableCurrent" was tagged by 3,392 real filers but had
no accounts_payable-shaped column anywhere in the schema - found via
scripts/xbrl_concept_coverage_scan.py's systematic gap scan, the first concrete candidate it
surfaced.

Live-confirmed via real companyfacts JSON: WMT FY2026 (period end 2026-01-31) =
$63,061,000,000, TGT FY2026 (period end 2026-01-31) = $12,622,000,000 - both sane, material
trade-payables figures.
"""

from typing import Any

from loaders.helpers.sec_base import SecEdgarStatementLoader
from loaders.load_financial_statements import _BALANCE_FIELD_MAPPING
from utils.external.sec_balance_sheet import get_balance_sheet


class _FakeClient:
    def __init__(self, facts: dict[str, Any]) -> None:
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0000000000"

    def get_company_facts(self, cik: str) -> dict[str, Any]:
        return {"facts": self._facts}


def _entry(year: int, val: float, filed: str, form: str = "10-K") -> dict[str, Any]:
    return {"end": f"{year}-12-31", "val": val, "filed": filed, "fp": "FY", "fy": year, "form": form}


class TestAccountsPayableCurrentWired:
    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_balance_sheet"
        loader.period = "annual"
        loader.statement_type = "balance"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "accounts_payable", "data_unavailable", "reason"})
        loader._field_mapping = {
            "accounts_payable": "accounts_payable",
            "accounts_payable_current": "accounts_payable",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset()
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        return loader

    def test_field_mapping_wires_accounts_payable_current(self) -> None:
        assert _BALANCE_FIELD_MAPPING["accounts_payable_current"] == "accounts_payable"

    def test_wmt_style_accounts_payable_recovered(self) -> None:
        loader = self._make_loader()
        row = {"symbol": "WMT", "fiscal_year": 2026, "accounts_payable_current": 63_061_000_000.0}

        transformed = loader.transform([row])

        assert transformed[0]["accounts_payable"] == 63_061_000_000.0

    def test_tgt_style_accounts_payable_recovered(self) -> None:
        loader = self._make_loader()
        row = {"symbol": "TGT", "fiscal_year": 2026, "accounts_payable_current": 12_622_000_000.0}

        transformed = loader.transform([row])

        assert transformed[0]["accounts_payable"] == 12_622_000_000.0

    def test_wmt_style_accounts_payable_maps_through_get_balance_sheet(self) -> None:
        facts = {
            "us-gaap": {
                "AccountsPayableCurrent": {"units": {"USD": [_entry(2026, 63_061_000_000.0, "2026-03-20")]}},
            },
            "ifrs-full": {},
        }
        rows = get_balance_sheet(_FakeClient(facts), "WMT", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}
        assert by_year[2026]["accounts_payable_current"] == 63_061_000_000.0
