"""Regression test for the 2026-09-05 fix (goal session: "SEC/XBRL missing data" sweep,
operating_income_not_itemized investigation): RRC (Range Resources, CIK 0000315852) and ARDT
(CIK 0001756655) both report a real "Revenues" and a real "CostsAndExpenses" total every fiscal
year but tag zero OperatingIncomeLoss facts anywhere in their companyfacts JSON - a single-step
income statement format this loader's other concepts never covered.

Live-confirmed via real SEC companyfacts JSON: RRC FY2025 Revenues=$3,115,515,000/
CostsAndExpenses=$2,283,825,000 (operating_income=$831,690,000), ARDT FY2025
Revenues=$6,324,339,000/CostsAndExpenses=$6,037,981,000 (operating_income=$286,358,000) - both
plausible operating margins once subtracted.

Writes to the "operating_income_loss" raw key (already mapped to the "operating_income" column)
rather than inventing a new bare "operating_income" key - see
income_tax_expense_pretax_income_wiring_gap_fixed_20260905 in memory for the "wiring
half-landed" bug class this avoids.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader
from loaders.load_financial_statements import _INCOME_FIELD_MAPPING
from utils.external.sec_statements import _fill_operating_income_from_revenue_minus_costs_and_expenses


class TestRrcArdtOperatingIncomeFromRevenueMinusCosts:
    def _make_loader(self) -> SecEdgarStatementLoader:
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_income_statement"
        loader.period = "annual"
        loader.statement_type = "income"
        loader._schema_cols = frozenset(
            {"symbol", "fiscal_year", "operating_income", "revenue", "data_unavailable", "reason"}
        )
        loader._field_mapping = dict(_INCOME_FIELD_MAPPING)
        loader._fallback_only_fields = frozenset()
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_exclusive_fields = frozenset()
        loader._reit_symbols = frozenset()
        loader._insurance_symbols = frozenset()
        return loader

    def test_rrc_style_operating_income_derived_and_survives_transform(self) -> None:
        rows = [
            {
                "symbol": "RRC",
                "fiscal_year": 2025,
                "revenues": 3_115_515_000.0,
                "costs_and_expenses": 2_283_825_000.0,
            }
        ]

        _fill_operating_income_from_revenue_minus_costs_and_expenses(rows)
        assert rows[0]["operating_income_loss"] == 831_690_000.0
        assert "costs_and_expenses" not in rows[0]

        transformed = self._make_loader().transform(rows)
        assert transformed[0]["operating_income"] == 831_690_000.0

    def test_ardt_style_operating_income_derived_and_survives_transform(self) -> None:
        rows = [
            {
                "symbol": "ARDT",
                "fiscal_year": 2025,
                "revenues": 6_324_339_000.0,
                "costs_and_expenses": 6_037_981_000.0,
            }
        ]

        _fill_operating_income_from_revenue_minus_costs_and_expenses(rows)
        assert rows[0]["operating_income_loss"] == 286_358_000.0

        transformed = self._make_loader().transform(rows)
        assert transformed[0]["operating_income"] == 286_358_000.0

    def test_never_overwrites_a_real_operating_income_value(self) -> None:
        rows = [
            {
                "symbol": "AAPL",
                "fiscal_year": 2025,
                "revenues": 400_000_000_000.0,
                "operating_income_loss": 120_000_000_000.0,
                "costs_and_expenses": 1.0,
            }
        ]

        _fill_operating_income_from_revenue_minus_costs_and_expenses(rows)

        assert rows[0]["operating_income_loss"] == 120_000_000_000.0
        assert "costs_and_expenses" not in rows[0]

    def test_requires_revenues_concept_specifically(self) -> None:
        rows = [{"symbol": "XYZ", "fiscal_year": 2025, "costs_and_expenses": 1_000_000.0}]

        _fill_operating_income_from_revenue_minus_costs_and_expenses(rows)

        assert rows[0].get("operating_income_loss") is None
