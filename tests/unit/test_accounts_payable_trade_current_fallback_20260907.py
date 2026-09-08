"""Regression test for the 2026-09-07 fix (goal session: XBRL concept-coverage backlog
sweep): "AccountsPayableTradeCurrent" was tagged by 485 real filers - 223 of them (46%,
including Abbott Labs, Air Products and Chemicals, Armstrong World Industries, Balchem,
Brown-Forman) tag NO "AccountsPayableCurrent" at all - and was never fetched, leaving
accounts_payable silently NULL for those filers.

Live-confirmed via the real on-disk companyfacts cache: 223/485 filers tagging
AccountsPayableTradeCurrent have zero AccountsPayableCurrent facts anywhere in their history.
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


class TestAccountsPayableTradeCurrentFallback:
    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_balance_sheet"
        loader.period = "annual"
        loader.statement_type = "balance"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "accounts_payable", "data_unavailable", "reason"})
        loader._field_mapping = {
            "accounts_payable": "accounts_payable",
            "accounts_payable_current": "accounts_payable",
            "accounts_payable_trade_current": "accounts_payable",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset({"accounts_payable_trade_current"})
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        return loader

    def test_field_mapping_wires_accounts_payable_trade_current(self) -> None:
        assert _BALANCE_FIELD_MAPPING["accounts_payable_trade_current"] == "accounts_payable"

    def test_abbott_style_no_plain_concept_recovers_via_trade_fallback(self) -> None:
        loader = self._make_loader()
        row = {"symbol": "ABT", "fiscal_year": 2026, "accounts_payable_trade_current": 4_567_000_000.0}

        transformed = loader.transform([row])

        assert transformed[0]["accounts_payable"] == 4_567_000_000.0

    def test_standard_concept_wins_when_filer_reports_both(self) -> None:
        facts = {
            "us-gaap": {
                "AccountsPayableTradeCurrent": {"units": {"USD": [_entry(2026, 999_000_000.0, "2026-03-20")]}},
                "AccountsPayableCurrent": {"units": {"USD": [_entry(2026, 63_061_000_000.0, "2026-03-20")]}},
            },
            "ifrs-full": {},
        }
        rows = get_balance_sheet(_FakeClient(facts), "WMT", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}
        assert by_year[2026]["accounts_payable_current"] == 63_061_000_000.0

    def test_trade_only_filer_recovers_via_get_balance_sheet(self) -> None:
        facts = {
            "us-gaap": {
                "AccountsPayableTradeCurrent": {"units": {"USD": [_entry(2026, 4_567_000_000.0, "2026-03-20")]}},
            },
            "ifrs-full": {},
        }
        rows = get_balance_sheet(_FakeClient(facts), "ABT", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}
        assert by_year[2026]["accounts_payable_trade_current"] == 4_567_000_000.0
