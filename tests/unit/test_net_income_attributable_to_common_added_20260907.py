"""Regression test for the 2026-09-07 fix (goal session: continuing the EPS-side NCI gap
documented in memory as eps_reconciliation_post_reload_nci_attributable_income_gap_20260907 -
EPS-side twin of migration 1265's balance-sheet noncontrolling_interest fix, migration 1270).

check_eps_reconciliation/check_basic_eps_reconciliation flag filers where
diluted_eps * shares_outstanding_diluted doesn't reconcile against net_income - legitimately,
because diluted/basic EPS is computed against net income attributable to COMMON shareholders
(net of noncontrolling interests and preferred dividends), not total consolidated net_income.
AAT (American Assets Trust, a REIT) live-confirmed: 10 straight fiscal years (2011-2020) with
diluted_eps * shares_outstanding_diluted landing at ~65-75% of net_income.

NetIncomeLossAvailableToCommonStockholdersDiluted is listed after ...Basic in
sec_income_statement.py's concepts list so it wins on overwrite for filers reporting both
(nets out preferred dividends too, a strictly more complete figure).
"""

from typing import Any

from loaders.helpers.sec_base import SecEdgarStatementLoader
from loaders.load_financial_statements import _INCOME_FIELD_MAPPING
from utils.external.sec_income_statement import get_income_statement


class _FakeClient:
    def __init__(self, facts: dict[str, Any]) -> None:
        self._facts = facts

    def symbol_to_cik(self, symbol: str) -> str:
        return "0000000000"

    def get_company_facts(self, cik: str) -> dict[str, Any]:
        return {"facts": self._facts}


def _entry(year: int, val: float, filed: str, form: str = "10-K") -> dict[str, Any]:
    return {"end": f"{year}-12-31", "val": val, "filed": filed, "fp": "FY", "fy": year, "form": form}


class TestNetIncomeAttributableToCommonWired:
    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_income_statement"
        loader.period = "annual"
        loader.statement_type = "income"
        loader._schema_cols = frozenset(
            {"symbol", "fiscal_year", "net_income_attributable_to_common", "data_unavailable", "reason"}
        )
        loader._field_mapping = {
            "net_income_loss_available_to_common_stockholders_basic": "net_income_attributable_to_common",
            "net_income_loss_available_to_common_stockholders_diluted": "net_income_attributable_to_common",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset()
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        return loader

    def test_field_mapping_wires_both_basic_and_diluted(self) -> None:
        assert (
            _INCOME_FIELD_MAPPING["net_income_loss_available_to_common_stockholders_basic"]
            == "net_income_attributable_to_common"
        )
        assert (
            _INCOME_FIELD_MAPPING["net_income_loss_available_to_common_stockholders_diluted"]
            == "net_income_attributable_to_common"
        )

    def test_diluted_wins_over_basic_when_both_present(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "AAT",
            "fiscal_year": 2020,
            "net_income_loss_available_to_common_stockholders_basic": 30_000_000.0,
            "net_income_loss_available_to_common_stockholders_diluted": 29_500_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["net_income_attributable_to_common"] == 29_500_000.0

    def test_basic_only_still_recovered(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "AAT",
            "fiscal_year": 2011,
            "net_income_loss_available_to_common_stockholders_basic": 12_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["net_income_attributable_to_common"] == 12_000_000.0

    def test_maps_through_get_income_statement(self) -> None:
        facts = {
            "us-gaap": {
                "NetIncomeLossAvailableToCommonStockholdersDiluted": {
                    "units": {"USD": [_entry(2020, 29_500_000.0, "2021-02-20")]}
                },
            },
            "ifrs-full": {},
        }
        rows = get_income_statement(_FakeClient(facts), "AAT", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}
        assert by_year[2020]["net_income_loss_available_to_common_stockholders_diluted"] == 29_500_000.0
