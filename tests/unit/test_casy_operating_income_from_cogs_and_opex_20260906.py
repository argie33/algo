"""Regression test for the 2026-09-06 fix (goal session: "SEC/XBRL missing data to zero"
sweep, operating_income_not_itemized investigation): Casey's General Stores (CASY, CIK
0000726958, $17.5B FY2026 revenue convenience-store/gas retailer) reports real "Revenues",
"CostOfGoodsAndServiceExcludingDepreciationDepletionAndAmortization",
"CostOfGoodsAndServicesSoldDepreciationAndAmortization", and "OperatingExpenses" but tags NO
OperatingIncomeLoss/CostsAndExpenses concept anywhere in its filing history - live-confirmed
via real companyfacts JSON. FY2026: $17,561,101,000 - $13,240,060,000 - $449,958,000 -
$2,837,426,000 = $1,033,657,000 (5.9% operating margin, plausible for this business model).
"""

from utils.external.sec_income_statement_fallbacks import (
    _fill_operating_income_from_revenue_minus_cogs_and_opex,
)


class TestCasyOperatingIncomeFromCogsAndOpex:
    def test_casy_style_operating_income_recovered(self) -> None:
        rows = [
            {
                "revenues": 17_561_101_000.0,
                "cost_of_goods_and_service_excluding_depreciation_depletion_and_amortization": 13_240_060_000.0,
                "cost_of_goods_and_services_sold_depreciation_and_amortization": 449_958_000.0,
                "operating_expenses": 2_837_426_000.0,
            }
        ]

        _fill_operating_income_from_revenue_minus_cogs_and_opex(rows)

        assert rows[0]["operating_income_loss"] == 1_033_657_000.0
        # Temp keys unique to this derivation must not leak downstream as unmapped fields.
        assert "operating_expenses" not in rows[0]
        assert "cost_of_goods_and_services_sold_depreciation_and_amortization" not in rows[0]

    def test_never_overwrites_a_real_operating_income_value(self) -> None:
        rows = [
            {
                "operating_income_loss": 999.0,
                "revenues": 17_561_101_000.0,
                "cost_of_goods_and_service_excluding_depreciation_depletion_and_amortization": 13_240_060_000.0,
                "cost_of_goods_and_services_sold_depreciation_and_amortization": 449_958_000.0,
                "operating_expenses": 2_837_426_000.0,
            }
        ]

        _fill_operating_income_from_revenue_minus_cogs_and_opex(rows)

        assert rows[0]["operating_income_loss"] == 999.0

    def test_does_not_fire_when_any_required_term_missing(self) -> None:
        rows = [
            {
                "revenues": 17_561_101_000.0,
                "cost_of_goods_and_service_excluding_depreciation_depletion_and_amortization": 13_240_060_000.0,
                # cogs_dda missing
                "operating_expenses": 2_837_426_000.0,
            }
        ]

        _fill_operating_income_from_revenue_minus_cogs_and_opex(rows)

        assert "operating_income_loss" not in rows[0]
        # OperatingExpenses is still popped even when the fallback doesn't fire, so it never
        # leaks as an unmapped-field warning for a filer this derivation doesn't apply to.
        assert "operating_expenses" not in rows[0]

    def test_accepts_plural_goods_sold_ex_dda_variant(self) -> None:
        rows = [
            {
                "revenues": 100.0,
                "cost_of_goods_sold_excluding_depreciation_depletion_and_amortization": 40.0,
                "cost_of_goods_and_services_sold_depreciation_and_amortization": 10.0,
                "operating_expenses": 20.0,
            }
        ]

        _fill_operating_income_from_revenue_minus_cogs_and_opex(rows)

        assert rows[0]["operating_income_loss"] == 30.0
