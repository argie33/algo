"""Regression test for the 2026-09-03 fix (goal session: "missing SEC/XBRL data under 6k"
sweep, accounts_receivable gap investigation): the primary balance-sheet "Receivables, net"
concept and its IFRS trade-receivables counterpart, for filers that never tag the standard
"AccountsReceivableNetCurrent"/"TradeAndOtherCurrentReceivables" concepts.

Live-confirmed via real companyfacts JSON:
- WMT (Walmart): "ReceivablesNetCurrent" $9,975,000,000 FY2025 / $11,172,000,000 FY2026.
- COST (Costco): "ReceivablesNetCurrent" $2,721,000,000 FY2024 / $3,203,000,000 FY2025.
- RTX (RTX Corp): reports both "AccountsReceivableNet" and "ReceivablesNetCurrent" with
  identical values ($14,701,000,000 FY2025) - confirms the two concepts are interchangeable
  for filers that tag "ReceivablesNetCurrent" as their primary balance-sheet line.
- TSM (Taiwan Semiconductor, IFRS): "CurrentTradeReceivables" $8,255,100,000 FY2024.
"""

from typing import Any

from loaders.helpers.sec_base import SecEdgarStatementLoader
from loaders.load_financial_statements import _BALANCE_FIELD_MAPPING, _DEBT_FALLBACK_ONLY_FIELDS
from utils.external.sec_statements import _BALANCE_IFRS_ALIASES, get_balance_sheet


class _FakeClient:
    def __init__(self, facts: dict[str, Any]) -> None:
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0000000000"

    def get_company_facts(self, cik: str) -> dict[str, Any]:
        return {"facts": self._facts}


def _entry(year: int, val: float, filed: str, form: str = "10-K") -> dict[str, Any]:
    return {"end": f"{year}-12-31", "val": val, "filed": filed, "fp": "FY", "fy": year, "form": form}


class TestReceivablesNetCurrentFallbackFixed:
    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_balance_sheet"
        loader.period = "annual"
        loader.statement_type = "balance"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "accounts_receivable", "data_unavailable", "reason"})
        loader._field_mapping = {
            "accounts_receivable": "accounts_receivable",
            "accounts_receivable_net_current": "accounts_receivable",
            "receivables_net_current": "accounts_receivable",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset({"receivables_net_current"})
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        return loader

    def test_field_mapping_wires_receivables_net_current(self) -> None:
        assert _BALANCE_FIELD_MAPPING["receivables_net_current"] == "accounts_receivable"
        assert "receivables_net_current" in _DEBT_FALLBACK_ONLY_FIELDS

    def test_wmt_style_accounts_receivable_recovered(self) -> None:
        loader = self._make_loader()
        row = {"symbol": "WMT", "fiscal_year": 2026, "receivables_net_current": 11_172_000_000.0}

        transformed = loader.transform([row])

        assert transformed[0]["accounts_receivable"] == 11_172_000_000.0

    def test_never_overwrites_a_real_accounts_receivable_value(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "RTX",
            "fiscal_year": 2025,
            "accounts_receivable_net_current": 14_701_000_000.0,
            "receivables_net_current": 1.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["accounts_receivable"] == 14_701_000_000.0


class TestTsmIfrsCurrentTradeReceivablesFixed:
    def test_alias_registered(self) -> None:
        assert ("CurrentTradeReceivables", "accounts_receivable_net_current") in _BALANCE_IFRS_ALIASES

    def test_tsm_style_current_trade_receivables_maps_through_get_balance_sheet(self) -> None:
        facts = {
            "us-gaap": {},
            "ifrs-full": {
                "CurrentTradeReceivables": {
                    "units": {"USD": [_entry(2024, 8_255_100_000.0, "2025-03-10", form="20-F")]}
                },
            },
        }
        rows = get_balance_sheet(_FakeClient(facts), "TSM", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}
        assert by_year[2024]["accounts_receivable_net_current"] == 8_255_100_000.0
