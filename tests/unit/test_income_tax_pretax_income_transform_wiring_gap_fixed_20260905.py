"""Regression test for the 2026-09-05 fix (goal session: "SEC/XBRL missing data" sweep):
sec_statements.py's `_fill_income_tax_expense_from_current_deferred_split()` and
`_fill_pretax_income_from_results_of_operations_when_validated()` both write their computed
result directly under the FINAL DB column name (`row["income_tax_expense"]` /
`row["pretax_income"]`), not a raw SEC-concept-derived key - unlike every other fallback in
`_INCOME_FIELD_MAPPING`, which map a concept's own snake-cased name to a column.

Neither bare key was ever a key in `_INCOME_FIELD_MAPPING`, so `transform()`'s
`if sec_field not in field_mapping` check silently discarded both values on every row that
reached this path - the CNS (income_tax_expense) and RRC (pretax_income) fixes those functions
were written for never actually landed in the database, despite each having a passing unit test:
those tests only exercised the pure fill function in isolation and never round-tripped the
result through `transform()`, so the gap passed CI undetected. Same "wiring half-landed" bug
class already caught twice before for a missing concept string - this time for a fill
function's own output key.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader
from loaders.load_financial_statements import _INCOME_FIELD_MAPPING


class TestIncomeTaxPretaxIncomeTransformWiringGapFixed:
    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_income_statement"
        loader.period = "annual"
        loader.statement_type = "income"
        loader._schema_cols = frozenset(
            {"symbol", "fiscal_year", "income_tax_expense", "pretax_income", "data_unavailable", "reason"}
        )
        loader._field_mapping = dict(_INCOME_FIELD_MAPPING)
        loader._fallback_only_fields = frozenset()
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_exclusive_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        return loader

    def test_field_mapping_has_identity_entries(self) -> None:
        assert _INCOME_FIELD_MAPPING["income_tax_expense"] == "income_tax_expense"
        assert _INCOME_FIELD_MAPPING["pretax_income"] == "pretax_income"

    def test_cns_style_income_tax_expense_survives_transform(self) -> None:
        loader = self._make_loader()
        row = {"symbol": "CNS", "fiscal_year": 2025, "income_tax_expense": 47_232_000.0}

        transformed = loader.transform([row])

        assert transformed[0]["income_tax_expense"] == 47_232_000.0

    def test_rrc_style_pretax_income_survives_transform(self) -> None:
        loader = self._make_loader()
        row = {"symbol": "RRC", "fiscal_year": 2022, "pretax_income": 1_413_830_000.0}

        transformed = loader.transform([row])

        assert transformed[0]["pretax_income"] == 1_413_830_000.0
