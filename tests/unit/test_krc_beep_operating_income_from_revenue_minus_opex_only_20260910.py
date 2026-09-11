"""Regression test for the 2026-09-10 fix (goal: "missing SEC/XBRL data under 300" push,
operating_income_not_itemized investigation): KRC (Kilroy Realty, office REIT) and BEEP
(Mobile Infrastructure Corp, parking-garage REIT) both report real "Revenues" and real
"OperatingExpenses" totals every fiscal year, tag ZERO cost-of-goods-sold-family concepts
anywhere (real estate operators don't sell goods), and stopped tagging OperatingIncomeLoss
directly in recent 10-Ks. Live-confirmed KRC FY2025: Revenues=$1,112,667,000 -
OperatingExpenses=$801,652,000 = $311,015,000 (28% operating margin).

Also verifies the danger case this fallback must never fall into: a filer (like CASY) whose
OperatingExpenses figure deliberately EXCLUDES a separately-tagged COGS line - subtracting
OperatingExpenses alone from revenue for such a filer would overstate operating income
(CASY's real margin is 5.9%, not the implausible ~84% naive subtraction would produce).
"""

from utils.external.sec_income_statement_fallbacks import (
    _fill_operating_income_from_revenue_minus_operating_expenses_only,
)


class TestKrcBeepOperatingIncomeFromRevenueMinusOpexOnly:
    def test_krc_style_operating_income_derived(self) -> None:
        rows = [
            {
                "symbol": "KRC",
                "fiscal_year": 2025,
                "revenues": 1_112_667_000.0,
                "operating_expenses": 801_652_000.0,
            }
        ]

        _fill_operating_income_from_revenue_minus_operating_expenses_only(rows)

        assert rows[0]["operating_income_loss"] == 311_015_000.0
        assert "operating_expenses" not in rows[0]

    def test_beep_style_operating_loss_derived(self) -> None:
        rows = [
            {
                "symbol": "BEEP",
                "fiscal_year": 2025,
                "revenues": 35_075_000.0,
                "operating_expenses": 38_217_000.0,
            }
        ]

        _fill_operating_income_from_revenue_minus_operating_expenses_only(rows)

        assert rows[0]["operating_income_loss"] == -3_142_000.0

    def test_never_fires_for_a_filer_that_tags_cogs_in_any_fiscal_year(self) -> None:
        rows = [
            {
                "symbol": "CASY",
                "fiscal_year": 2024,
                "revenues": 15_000_000_000.0,
                "operating_expenses": 2_500_000_000.0,
            },
            {
                "symbol": "CASY",
                "fiscal_year": 2026,
                "revenues": 17_561_101_000.0,
                "operating_expenses": 2_837_426_000.0,
                # A COGS-family concept tagged in a DIFFERENT fiscal year - still must
                # block the fallback for every row of this filer, not just this one.
                "cost_of_goods_sold_excluding_depreciation_depletion_and_amortization": 13_240_060_000.0,
            },
        ]

        _fill_operating_income_from_revenue_minus_operating_expenses_only(rows)

        assert rows[0].get("operating_income_loss") is None
        assert rows[1].get("operating_income_loss") is None
        # Untouched - the sibling cogs_and_opex fallback still needs this key.
        assert rows[0]["operating_expenses"] == 2_500_000_000.0
        assert rows[1]["operating_expenses"] == 2_837_426_000.0

    def test_never_fires_for_an_insurer_whose_opex_excludes_claims_incurred(self) -> None:
        rows = [
            {
                "symbol": "ITIC",
                "fiscal_year": 2025,
                "revenues": 272_755_000.0,
                "operating_expenses": 44_549_000.0,
                "benefits_losses_and_expenses": 200_000_000.0,
            }
        ]

        _fill_operating_income_from_revenue_minus_operating_expenses_only(rows)

        assert rows[0].get("operating_income_loss") is None
        assert rows[0]["operating_expenses"] == 44_549_000.0

    def test_never_overwrites_a_real_operating_income_value(self) -> None:
        rows = [
            {
                "symbol": "AAPL",
                "fiscal_year": 2025,
                "revenues": 400_000_000_000.0,
                "operating_income_loss": 120_000_000_000.0,
                "operating_expenses": 1.0,
            }
        ]

        _fill_operating_income_from_revenue_minus_operating_expenses_only(rows)

        assert rows[0]["operating_income_loss"] == 120_000_000_000.0
        assert rows[0]["operating_expenses"] == 1.0

    def test_requires_both_revenues_and_operating_expenses(self) -> None:
        rows = [{"symbol": "XYZ", "fiscal_year": 2025, "operating_expenses": 1_000_000.0}]

        _fill_operating_income_from_revenue_minus_operating_expenses_only(rows)

        assert rows[0].get("operating_income_loss") is None
