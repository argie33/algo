"""Regression test for the 2026-09-03 fix (goal session: "missing SEC/XBRL data under 6k"
sweep, ebitda_not_extracted investigation): several large, well-known filers stopped
tagging plain "DepreciationAndAmortization" and switched to the combined depreciation +
depletion + amortization concept "DepreciationDepletionAndAmortization" instead.

Live-confirmed via real SEC companyfacts JSON: PG (Procter & Gamble) FY2026
$3,160,000,000, WM (Waste Management) FY2025 $2,863,000,000, ULTA (Ulta Beauty) FY2025
(period ended 2026-01-31) $300,772,000, WSM (Williams-Sonoma) and CP (Canadian Pacific
Kansas City) also confirmed - all real, current, growing figures with zero data under
DepreciationAndAmortization for recent years. Same target column
("amortization_expense") as DepreciationAndAmortization, matching that concept's existing
"combined D&A total" semantics - not a new column.

Missing D&A silently understated EBITDA (load_sec_valuations.py's ebitda = operating_income
+ depreciation_expense + amortization_expense only adds whichever inputs are present,
so a missing D&A doesn't null EBITDA out - it just produces a smaller-than-true value)
for these filers, in addition to the ebitda_not_extracted coverage gap for symbols where
operating_income was also unavailable.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader
from loaders.load_financial_statements import _INCOME_FIELD_MAPPING


class TestCombinedDdaTaxonomyTransitionFixed:
    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_income_statement"
        loader.period = "annual"
        loader.statement_type = "income"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "amortization_expense", "data_unavailable", "reason"})
        loader._field_mapping = {
            "depreciation_and_amortization": "amortization_expense",
            "depreciation_depletion_and_amortization": "amortization_expense",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset()
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        return loader

    def test_field_mapping_wires_concept_to_amortization_expense(self) -> None:
        assert _INCOME_FIELD_MAPPING["depreciation_depletion_and_amortization"] == "amortization_expense"

    def test_pg_style_combined_dda_recovered(self) -> None:
        loader = self._make_loader()
        row = {
            "symbol": "PG",
            "fiscal_year": 2026,
            "depreciation_depletion_and_amortization": 3_160_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["amortization_expense"] == 3_160_000_000.0
