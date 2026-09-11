"""Regression test for the 2026-09-10 fix (goal: "missing SEC/XBRL data under 300" push,
operating_income_not_itemized re-investigation continuation): CPT (Camden Property Trust,
apartment REIT) and CRVL (CorVel Corp) both have real, fully-mapped revenue/cost_of_revenue/
operating_expenses on their final annual_income_statement row but no OperatingIncomeLoss/
CostsAndExpenses concept anywhere in their filing history, so operating_income stayed NULL
despite a real, derivable value sitting right there. Live-confirmed CPT FY2025:
revenue=$1,573,544,000 - cost_of_revenue=$566,710,000 - operating_expenses=$79,344,000 =
$927,490,000 (59% margin before depreciation).

This is the post-field-mapping sibling of utils/external/sec_income_statement_fallbacks.py's
KRC/BEEP (_fill_operating_income_from_revenue_minus_operating_expenses_only) and CASY
(_fill_operating_income_from_revenue_minus_cogs_and_opex) derivations, which both operate on
raw, pre-mapping concept-derived row keys and so never fire for CPT/CRVL: CPT's real revenue
sits under "operating_lease_lease_income" (a REIT-exclusive field) until
_INCOME_FIELD_MAPPING consolidates it into "revenue", and CPT/CRVL's COGS is a single,
unsplit concept (not CASY's ex-D&A/D&A pair) that only becomes "cost_of_revenue" at the same
later stage - a raw-stage fallback keyed on canonical names never sees them.
"""

from loaders.helpers.financial_statements_value_validation import FinancialStatementsValueValidationMixin


class _FakeLoader(FinancialStatementsValueValidationMixin):
    table_name = "annual_income_statement"
    statement_type = "income"
    period = "annual"

    def _record_explicit_null_rejection(self, row: dict, field: str, reason: str) -> None:
        pass


class TestCptCrvlOperatingIncomeFromRevenueCostAndOpex:
    def test_cpt_style_operating_income_derived(self) -> None:
        rows = [
            {
                "symbol": "CPT",
                "fiscal_year": 2025,
                "revenue": 1_573_544_000.0,
                "cost_of_revenue": 566_710_000.0,
                "operating_expenses": 79_344_000.0,
                "operating_income": None,
            }
        ]

        _FakeLoader()._fill_operating_income_from_revenue_cost_and_opex(rows)

        assert rows[0]["operating_income"] == 927_490_000.0

    def test_crvl_style_operating_income_derived(self) -> None:
        rows = [
            {
                "symbol": "CRVL",
                "fiscal_year": 2025,
                "revenue": 895_589_000.0,
                "cost_of_revenue": 685_861_000.0,
                "operating_expenses": 88_904_000.0,
                "operating_income": None,
            }
        ]

        _FakeLoader()._fill_operating_income_from_revenue_cost_and_opex(rows)

        assert rows[0]["operating_income"] == 120_824_000.0

    def test_negative_operating_income_derived(self) -> None:
        rows = [
            {
                "symbol": "MNDR",
                "fiscal_year": 2025,
                "revenue": 7_646_739.0,
                "cost_of_revenue": 6_366_621.0,
                "operating_expenses": 2_669_395.0,
                "operating_income": None,
            }
        ]

        _FakeLoader()._fill_operating_income_from_revenue_cost_and_opex(rows)

        assert rows[0]["operating_income"] == -1_389_277.0

    def test_never_overwrites_a_real_operating_income(self) -> None:
        rows = [
            {
                "symbol": "REAL",
                "fiscal_year": 2025,
                "revenue": 100.0,
                "cost_of_revenue": 50.0,
                "operating_expenses": 10.0,
                "operating_income": 5.0,
            }
        ]

        _FakeLoader()._fill_operating_income_from_revenue_cost_and_opex(rows)

        assert rows[0]["operating_income"] == 5.0

    def test_no_derivation_when_any_input_missing(self) -> None:
        rows = [
            {
                "symbol": "PARTIAL",
                "fiscal_year": 2025,
                "revenue": 100.0,
                "cost_of_revenue": None,
                "operating_expenses": 10.0,
                "operating_income": None,
            }
        ]

        _FakeLoader()._fill_operating_income_from_revenue_cost_and_opex(rows)

        assert rows[0]["operating_income"] is None
