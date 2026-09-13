"""Regression test for the 2026-09-13 fix (goal session: check_balance_sheet_identity
512-symbol/year WARN bucket triage): "RedeemableNoncontrollingInterestEquityOtherCarryingAmount"
is a sibling mezzanine-equity concept to "TemporaryEquityCarryingAmountAttributableToParent"
(see test_audit_tie_out_temporary_equity_20260911.py for that concept's own fix) but had no
mapping anywhere.

Live-confirmed via real companyfacts JSON: PROK (Prokidney Corp) FY2025 10-K (period end
2025-12-31) tags Assets=$335,574,000, Liabilities=$34,781,000,
StockholdersEquity=-$1,011,197,000, and RedeemableNoncontrollingInterestEquityOtherCarryingAmount
=$1,311,990,000 - exactly closing the balance-sheet identity gap ($335,574,000 ==
$34,781,000 + $1,311,990,000 + -$1,011,197,000).
"""

from typing import Any

from loaders.helpers.sec_base import SecEdgarStatementLoader
from loaders.load_financial_statements import _BALANCE_FIELD_MAPPING
from utils.external.sec_balance_sheet import get_balance_sheet


class _FakeClient:
    def __init__(self, facts: dict[str, Any]) -> None:
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0001960201"

    def get_company_facts(self, cik: str) -> dict[str, Any]:
        return {"facts": self._facts}


def _entry(year: int, val: float, filed: str, end: str, form: str = "10-K") -> dict[str, Any]:
    return {"end": end, "val": val, "filed": filed, "fp": "FY", "fy": year, "form": form}


class TestRedeemableNciTemporaryEquityWired:
    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_balance_sheet"
        loader.period = "annual"
        loader.statement_type = "balance"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "temporary_equity", "data_unavailable", "reason"})
        loader._field_mapping = {
            "temporary_equity": "temporary_equity",
            "redeemable_noncontrolling_interest_equity_other_carrying_amount": "temporary_equity",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset()
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        return loader

    def test_field_mapping_wires_redeemable_nci_to_temporary_equity(self) -> None:
        assert (
            _BALANCE_FIELD_MAPPING["redeemable_noncontrolling_interest_equity_other_carrying_amount"]
            == "temporary_equity"
        )

    def test_prok_style_redeemable_nci_recovered(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "PROK",
            "fiscal_year": 2025,
            "redeemable_noncontrolling_interest_equity_other_carrying_amount": 1_311_990_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["temporary_equity"] == 1_311_990_000.0

    def test_prok_style_temporary_equity_maps_through_get_balance_sheet(self) -> None:
        facts = {
            "us-gaap": {
                "Assets": {"units": {"USD": [_entry(2025, 335_574_000.0, "2026-03-18", "2025-12-31")]}},
                "Liabilities": {"units": {"USD": [_entry(2025, 34_781_000.0, "2026-03-18", "2025-12-31")]}},
                "StockholdersEquity": {"units": {"USD": [_entry(2025, -1_011_197_000.0, "2026-03-18", "2025-12-31")]}},
                "RedeemableNoncontrollingInterestEquityOtherCarryingAmount": {
                    "units": {"USD": [_entry(2025, 1_311_990_000.0, "2026-03-18", "2025-12-31")]}
                },
            },
            "ifrs-full": {},
        }
        rows = get_balance_sheet(_FakeClient(facts), "PROK", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}
        assert by_year[2025]["redeemable_noncontrolling_interest_equity_other_carrying_amount"] == 1_311_990_000.0

    def test_prok_style_identity_closes_with_temporary_equity(self) -> None:
        assets = 335_574_000.0
        liabilities = 34_781_000.0
        stockholders_equity = -1_011_197_000.0
        temporary_equity = 1_311_990_000.0

        assert assets == liabilities + stockholders_equity + temporary_equity
