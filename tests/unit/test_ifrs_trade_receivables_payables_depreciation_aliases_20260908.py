"""Regression test for the 2026-09-08 IFRS "TradeReceivables"/"TradeAndOtherCurrentPayables"/
"DepreciationAndAmortisationExpense" aliases (goal session: XBRL coverage-scan backlog triage,
follow-up to the same day's Borrowings/NoncontrollingInterests aliases).

"TradeReceivables" - live-confirmed via Himax Technologies' real companyfacts JSON (CIK
0001342338): FY2024 (period end 2024-12-31) TradeReceivables=USD 89,527,000, a sane ~7.7% of
that year's CurrentAssets (USD 1,168,043,000), with none of the concepts already aliased to
"accounts_receivable_net_current" (TradeAndOtherCurrentReceivables/CurrentTradeReceivables)
tagged at all for this filer.

"TradeAndOtherCurrentPayables" - live-confirmed via Agnico Eagle's real companyfacts JSON (CIK
0000002809): FY2025 (period end 2025-12-31) TradeAndOtherCurrentPayables=USD 1,033,444,000, a
sane ~42% of that same period's CurrentLiabilities (USD 2,472,206,000).

"DepreciationAndAmortisationExpense" - live-confirmed via Bank of Nova Scotia's real
companyfacts JSON (CIK 0000009631): FY2025 (period end 2025-10-31)
DepreciationAndAmortisationExpense=CAD 1,604,000,000, a separate real XBRL element from
"DepreciationAndAmortisation" (never tagged by BNS at all).
"""

from typing import Any

from utils.external.sec_balance_sheet import get_balance_sheet
from utils.external.sec_income_statement import get_income_statement


class _FakeClient:
    def __init__(self, facts: dict[str, Any]) -> None:
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0000000000"

    def get_company_facts(self, cik: str) -> dict[str, Any]:
        return {"facts": self._facts}


def _entry(year: int, val: float, filed: str, form: str = "20-F") -> dict[str, Any]:
    return {"end": f"{year}-12-31", "val": val, "filed": filed, "fp": "FY", "fy": year, "form": form}


class TestIfrsTradeReceivablesAlias:
    def test_trade_receivables_maps_to_accounts_receivable(self) -> None:
        facts = {
            "us-gaap": {},
            "ifrs-full": {
                "TradeReceivables": {"units": {"USD": [_entry(2024, 89_527_000.0, "2025-04-02")]}},
            },
        }
        rows = get_balance_sheet(_FakeClient(facts), "HIMX", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}
        assert by_year[2024]["accounts_receivable_net_current"] == 89_527_000.0

    def test_current_trade_receivables_wins_over_trade_receivables_fallback(self) -> None:
        # A filer reporting both keeps the more-established concept - TradeReceivables never
        # overwrites it (first-populated-wins for cross-concept collisions in the same year).
        facts = {
            "us-gaap": {},
            "ifrs-full": {
                "CurrentTradeReceivables": {"units": {"USD": [_entry(2024, 18_700_000.0, "2025-04-02")]}},
                "TradeReceivables": {"units": {"USD": [_entry(2024, 18_690_000.0, "2025-04-02")]}},
            },
        }
        rows = get_balance_sheet(_FakeClient(facts), "AEM", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}
        assert by_year[2024]["accounts_receivable_net_current"] == 18_700_000.0


class TestIfrsTradeAndOtherCurrentPayablesAlias:
    def test_maps_to_accounts_payable_current(self) -> None:
        facts = {
            "us-gaap": {},
            "ifrs-full": {
                "TradeAndOtherCurrentPayables": {"units": {"USD": [_entry(2025, 1_033_444_000.0, "2026-02-13")]}},
            },
        }
        rows = get_balance_sheet(_FakeClient(facts), "AEM", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}
        assert by_year[2025]["accounts_payable_current"] == 1_033_444_000.0


class TestIfrsDepreciationAndAmortisationExpenseAlias:
    def test_maps_to_depreciation_and_amortization(self) -> None:
        facts = {
            "us-gaap": {},
            "ifrs-full": {
                "DepreciationAndAmortisationExpense": {
                    "units": {"USD": [_entry(2025, 1_604_000_000.0, "2025-12-02", form="40-F")]}
                },
            },
        }
        rows = get_income_statement(_FakeClient(facts), "BNS", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}
        assert by_year[2025]["depreciation_and_amortization"] == 1_604_000_000.0
