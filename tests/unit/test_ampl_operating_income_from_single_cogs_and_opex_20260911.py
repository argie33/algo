"""Regression test for the 2026-09-11 fix (goal: "missing SEC/XBRL data under 300" push,
operating_income_not_itemized re-investigation): AMPL (Amplitude Inc) tags a single, unsplit
"CostOfGoodsAndServicesSold" (not CASY's D&A-split pair) plus a real "OperatingExpenses" total
that excludes it, but never tags OperatingIncomeLoss/CostsAndExpenses. Live-confirmed FY2025:
revenue $343,214,000 - cost_of_revenue $89,286,000 - operating_expenses $349,933,000 =
-$96,005,000, matching yfinance's independently-parsed Operating Income for the same fiscal
year exactly.
"""

from utils.external.sec_income_statement_fallbacks import (
    _fill_operating_income_from_revenue_minus_single_cogs_and_opex,
)


class TestAmplOperatingIncomeFromSingleCogsAndOpex:
    def test_ampl_style_operating_loss_derived(self) -> None:
        rows = [
            {
                "symbol": "AMPL",
                "fiscal_year": 2025,
                "revenues": 343_214_000.0,
                "cost_of_revenue": 89_286_000.0,
                "operating_expenses": 349_933_000.0,
            }
        ]

        _fill_operating_income_from_revenue_minus_single_cogs_and_opex(rows)

        assert rows[0]["operating_income_loss"] == -96_005_000.0
        assert "operating_expenses" not in rows[0]

    def test_falls_back_to_cost_of_goods_and_services_sold_key(self) -> None:
        rows = [
            {
                "symbol": "AMPL",
                "fiscal_year": 2024,
                "revenues": 299_272_000.0,
                "cost_of_goods_and_services_sold": 76_924_000.0,
                "operating_expenses": 329_731_000.0,
            }
        ]

        _fill_operating_income_from_revenue_minus_single_cogs_and_opex(rows)

        assert rows[0]["operating_income_loss"] == -107_383_000.0

    def test_never_fires_for_a_casy_shaped_dda_split_cogs_row(self) -> None:
        rows = [
            {
                "symbol": "CASY",
                "fiscal_year": 2026,
                "revenues": 17_561_101_000.0,
                "cost_of_goods_sold_excluding_depreciation_depletion_and_amortization": 13_240_060_000.0,
                "cost_of_goods_and_services_sold_depreciation_and_amortization": 449_958_000.0,
                "operating_expenses": 2_837_426_000.0,
            }
        ]

        _fill_operating_income_from_revenue_minus_single_cogs_and_opex(rows)

        assert rows[0].get("operating_income_loss") is None
        # Untouched - the sibling 4-value fallback still needs this key.
        assert rows[0]["operating_expenses"] == 2_837_426_000.0

    def test_never_overwrites_a_real_operating_income_value(self) -> None:
        rows = [
            {
                "symbol": "XYZ",
                "fiscal_year": 2025,
                "revenues": 1_000_000.0,
                "cost_of_revenue": 100.0,
                "operating_income_loss": 500_000.0,
                "operating_expenses": 1.0,
            }
        ]

        _fill_operating_income_from_revenue_minus_single_cogs_and_opex(rows)

        assert rows[0]["operating_income_loss"] == 500_000.0
        assert rows[0]["operating_expenses"] == 1.0

    def test_requires_cost_of_revenue_and_operating_expenses_and_revenue(self) -> None:
        rows = [{"symbol": "XYZ", "fiscal_year": 2025, "operating_expenses": 1_000_000.0}]

        _fill_operating_income_from_revenue_minus_single_cogs_and_opex(rows)

        assert rows[0].get("operating_income_loss") is None
