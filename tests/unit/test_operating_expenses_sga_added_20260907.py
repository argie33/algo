"""Regression test for the 2026-09-07 fix (goal session: XBRL concept coverage scanner
follow-up, migration 1264): "SellingGeneralAndAdministrativeExpense" was tagged by 2,820+ real
filers but had no operating_expenses/SG&A-shaped column anywhere in the schema - found via
scripts/xbrl_concept_coverage_scan.py's systematic gap scan.

Live-confirmed via real companyfacts JSON: WMT FY2026 (period end 2026-01-31) =
$147,943,000,000, TGT FY2026 (period end 2026-01-31) = $21,535,000,000 - both sane SG&A
figures relative to revenue.
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


class TestSellingGeneralAndAdministrativeExpenseWired:
    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_income_statement"
        loader.period = "annual"
        loader.statement_type = "income"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "operating_expenses", "data_unavailable", "reason"})
        loader._field_mapping = {
            "operating_expenses": "operating_expenses",
            "selling_general_and_administrative_expense": "operating_expenses",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset()
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        return loader

    def test_field_mapping_wires_selling_general_and_administrative_expense(self) -> None:
        assert _INCOME_FIELD_MAPPING["selling_general_and_administrative_expense"] == "operating_expenses"

    def test_wmt_style_operating_expenses_recovered(self) -> None:
        loader = self._make_loader()
        row = {"symbol": "WMT", "fiscal_year": 2026, "selling_general_and_administrative_expense": 147_943_000_000.0}

        transformed = loader.transform([row])

        assert transformed[0]["operating_expenses"] == 147_943_000_000.0

    def test_tgt_style_operating_expenses_recovered(self) -> None:
        loader = self._make_loader()
        row = {"symbol": "TGT", "fiscal_year": 2026, "selling_general_and_administrative_expense": 21_535_000_000.0}

        transformed = loader.transform([row])

        assert transformed[0]["operating_expenses"] == 21_535_000_000.0

    def test_wmt_style_operating_expenses_maps_through_get_income_statement(self) -> None:
        facts = {
            "us-gaap": {
                "SellingGeneralAndAdministrativeExpense": {
                    "units": {"USD": [_entry(2026, 147_943_000_000.0, "2026-03-20")]}
                },
            },
            "ifrs-full": {},
        }
        rows = get_income_statement(_FakeClient(facts), "WMT", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}
        assert by_year[2026]["selling_general_and_administrative_expense"] == 147_943_000_000.0
