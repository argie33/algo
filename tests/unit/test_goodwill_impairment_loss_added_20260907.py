"""Regression test for the 2026-09-07 fix (goal session: XBRL extraction/tie-out hardening
follow-up, migration 1271): "GoodwillImpairmentLoss" was tagged by 2,567 real filers but had
no goodwill_impairment_loss-shaped column anywhere in the schema - found via
scripts/xbrl_concept_coverage_scan.py's systematic gap scan.

This is a P&L (income-statement) concept - the period impairment CHARGE taken against
goodwill - distinct from annual_balance_sheet.goodwill (the balance-sheet carrying amount,
already extracted) and from _reject_implausible_goodwill's sanity check on that balance-sheet
figure (unrelated to this new column).

Live-confirmed via real companyfacts JSON: Kraft Heinz Co FY2025 (period end 2025-12-27) =
$6,734,000,000, CVS Health Corporation FY2025 (period end 2025-12-31) = $5,725,000,000 - both
real, material impairment charges consistent with each company's well-known recent goodwill
write-downs.
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


class TestGoodwillImpairmentLossWired:
    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_income_statement"
        loader.period = "annual"
        loader.statement_type = "income"
        loader._schema_cols = frozenset(
            {"symbol", "fiscal_year", "goodwill_impairment_loss", "data_unavailable", "reason"}
        )
        loader._field_mapping = {
            "goodwill_impairment_loss": "goodwill_impairment_loss",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset()
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        return loader

    def test_field_mapping_wires_goodwill_impairment_loss(self) -> None:
        assert _INCOME_FIELD_MAPPING["goodwill_impairment_loss"] == "goodwill_impairment_loss"

    def test_kraft_heinz_style_goodwill_impairment_loss_recovered(self) -> None:
        loader = self._make_loader()
        row = {"symbol": "KHC", "fiscal_year": 2025, "goodwill_impairment_loss": 6_734_000_000.0}

        transformed = loader.transform([row])

        assert transformed[0]["goodwill_impairment_loss"] == 6_734_000_000.0

    def test_cvs_style_goodwill_impairment_loss_recovered(self) -> None:
        loader = self._make_loader()
        row = {"symbol": "CVS", "fiscal_year": 2025, "goodwill_impairment_loss": 5_725_000_000.0}

        transformed = loader.transform([row])

        assert transformed[0]["goodwill_impairment_loss"] == 5_725_000_000.0

    def test_kraft_heinz_style_goodwill_impairment_loss_maps_through_get_income_statement(self) -> None:
        facts = {
            "us-gaap": {
                "GoodwillImpairmentLoss": {"units": {"USD": [_entry(2025, 6_734_000_000.0, "2026-02-13")]}},
            },
            "ifrs-full": {},
        }
        rows = get_income_statement(_FakeClient(facts), "KHC", period="annual")
        by_year = {r["fiscal_year"]: r for r in rows}
        assert by_year[2025]["goodwill_impairment_loss"] == 6_734_000_000.0

    def test_naturally_sparse_row_without_goodwill_impairment_loss_is_unaffected(self) -> None:
        """Most company-years have no goodwill impairment (episodic, not recurring) - the
        field must simply be absent/None, not treated as an error."""
        loader = self._make_loader()
        row = {"symbol": "AAPL", "fiscal_year": 2025}

        transformed = loader.transform([row])

        assert transformed[0].get("goodwill_impairment_loss") is None
