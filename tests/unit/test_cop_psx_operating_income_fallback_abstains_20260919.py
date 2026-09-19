"""Regression test for the 2026-09-19 fix (/goal data-confidence audit, XBRL crosscheck backlog
triage): COP (ConocoPhillips) and PSX (Phillips 66) both have real, fully-mapped revenue/
cost_of_revenue/operating_expenses on their final annual_income_statement row, so
_fill_operating_income_from_revenue_cost_and_opex's narrow revenue-cost_of_revenue-
operating_expenses(SG&A-only) formula fires - but both oil majors have several other real,
separately-tagged operating cost lines (production/operating costs, exploration expenses, DD&A,
impairments, taxes-other-than-income, accretion) that this pipeline has no canonical column for,
so the fallback silently omits them and inflates operating_income. Live-verified against COP's
own FY2025 R3.htm (accession 0001163165-26-000009): the fallback formula alone would yield
$35,726,000,000, ~$24.8B above the correct ~$11,316M value (revenue minus all 7 real cost
lines, within 0.3% of yfinance's $11,342M). See cop_operating_income_narrow_fallback_gap_20260919
memory note for the full mechanism and the PSX/OXY/BP/PBR triage that led here.

Correctly deriving the value needs new raw-concept extraction this pipeline doesn't have yet, so
until that lands, the fallback abstains (leaves operating_income NULL) for these two symbols
rather than storing a confidently-wrong inflated figure that feeds Quality/Value scores - same
doctrine as the CPT/CRVL-derivation sibling test file's "never overwrites a real value" case,
just for "never derives a known-wrong one" instead.
"""

from loaders.helpers.financial_statements_value_validation import FinancialStatementsValueValidationMixin


class _FakeLoader(FinancialStatementsValueValidationMixin):
    table_name = "annual_income_statement"
    statement_type = "income"
    period = "annual"

    def _record_explicit_null_rejection(self, row: dict, field: str, reason: str) -> None:
        pass


class TestCopPsxOperatingIncomeFallbackAbstains:
    def test_cop_fallback_abstains_rather_than_deriving_inflated_value(self) -> None:
        rows = [
            {
                "symbol": "COP",
                "fiscal_year": 2025,
                "revenue": 58_944_000_000.0,
                "cost_of_revenue": 22_325_000_000.0,
                "operating_expenses": 893_000_000.0,
                "operating_income": None,
            }
        ]

        _FakeLoader()._fill_operating_income_from_revenue_cost_and_opex(rows)

        assert rows[0]["operating_income"] is None

    def test_psx_fallback_abstains_rather_than_deriving_inflated_value(self) -> None:
        rows = [
            {
                "symbol": "PSX",
                "fiscal_year": 2025,
                "revenue": 132_376_000_000.0,
                "cost_of_revenue": 116_093_000_000.0,
                "operating_expenses": 2_437_000_000.0,
                "operating_income": None,
            }
        ]

        _FakeLoader()._fill_operating_income_from_revenue_cost_and_opex(rows)

        assert rows[0]["operating_income"] is None

    def test_unrelated_symbol_still_derives_normally(self) -> None:
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
