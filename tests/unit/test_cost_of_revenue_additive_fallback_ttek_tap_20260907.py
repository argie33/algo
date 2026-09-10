"""Regression test for the 2026-09-07 fix (goal session: stock_scores factor audit + tie-out
CI sweep, gross_profit_identity live triage): Tetra Tech (TTEK, CIK 0000831641, $5.44B FY2025
revenue environmental/engineering consulting firm) tags real subcontractor/pass-through project
costs under "OtherCostOfOperatingRevenue" ($3,656,016,000 FY2025) SEPARATE from its main
"CostOfGoodsAndServicesSold" ($825,230,000) - live-confirmed via real SEC companyfacts JSON:
only their SUM ($4,481,246,000) reconciles with TTEK's own filed GrossProfit ($961,344,000 =
$5,442,590,000 revenue - $4,481,246,000, exact to the dollar).

Extended same-day (same goal session continuation) to also sum "ExciseAndSalesTaxes" for
Molson Coors (TAP/TAP.A, CIK 0000024545, $13.04B FY2025 revenue brewer): $13,040,300,000
revenue - $6,866,200,000 CostOfGoodsAndServicesSold - $1,899,500,000 ExciseAndSalesTaxes =
$4,274,600,000, exact match to TAP's own tagged GrossProfit. Peer-checked Boston Beer (SAM):
its Revenues - CostOfGoodsAndServicesSold already reconciles exactly with no excise-tax
adjustment needed, ruling out a blanket alcoholic-beverage-industry pattern.
"""

from utils.external.sec_income_statement_fallbacks import (
    _fill_cost_of_revenue_from_other_operating_cost,
)


class TestTtekCostOfRevenueFromOtherOperatingCost:
    def test_ttek_style_cost_of_revenue_corrected(self) -> None:
        rows = [
            {
                "revenue_from_contract_with_customer_excluding_assessed_tax": 5_442_590_000.0,
                "cost_of_goods_and_services_sold": 825_230_000.0,
                "other_cost_of_operating_revenue": 3_656_016_000.0,
                "gross_profit": 961_344_000.0,
            }
        ]

        _fill_cost_of_revenue_from_other_operating_cost(rows)

        assert rows[0]["cost_of_goods_and_services_sold"] == 4_481_246_000.0
        implied_gp = (
            rows[0]["revenue_from_contract_with_customer_excluding_assessed_tax"]
            - rows[0]["cost_of_goods_and_services_sold"]
        )
        assert implied_gp == rows[0]["gross_profit"]
        # Temp key unique to this derivation must not leak downstream as an unmapped field.
        assert "other_cost_of_operating_revenue" not in rows[0]

    def test_does_not_fire_when_other_cost_absent(self) -> None:
        rows = [{"cost_of_goods_and_services_sold": 825_230_000.0}]

        _fill_cost_of_revenue_from_other_operating_cost(rows)

        assert rows[0]["cost_of_goods_and_services_sold"] == 825_230_000.0

    def test_does_not_fire_when_cogs_absent(self) -> None:
        rows = [{"other_cost_of_operating_revenue": 3_656_016_000.0}]

        _fill_cost_of_revenue_from_other_operating_cost(rows)

        assert "cost_of_goods_and_services_sold" not in rows[0]
        # Still strips the raw key so it never leaks as an unmapped field for a filer
        # this derivation doesn't apply to (e.g. one with no COGS concept tagged at all).
        assert "other_cost_of_operating_revenue" not in rows[0]

    def test_no_op_for_a_filer_with_neither_concept(self) -> None:
        rows = [{"revenues": 100.0}]

        _fill_cost_of_revenue_from_other_operating_cost(rows)

        assert rows[0] == {"revenues": 100.0}

    def test_tap_style_excise_tax_summed_in(self) -> None:
        rows = [
            {
                "revenue_from_contract_with_customer_excluding_assessed_tax": 13_040_300_000.0,
                "cost_of_goods_and_services_sold": 6_866_200_000.0,
                "excise_and_sales_taxes": 1_899_500_000.0,
                "gross_profit": 4_274_600_000.0,
            }
        ]

        _fill_cost_of_revenue_from_other_operating_cost(rows)

        assert rows[0]["cost_of_goods_and_services_sold"] == 8_765_700_000.0
        implied_gp = (
            rows[0]["revenue_from_contract_with_customer_excluding_assessed_tax"]
            - rows[0]["cost_of_goods_and_services_sold"]
        )
        assert implied_gp == rows[0]["gross_profit"]
        assert "excise_and_sales_taxes" not in rows[0]

    def test_both_extra_concepts_summed_together(self) -> None:
        rows = [
            {
                "cost_of_goods_and_services_sold": 100.0,
                "other_cost_of_operating_revenue": 10.0,
                "excise_and_sales_taxes": 5.0,
            }
        ]

        _fill_cost_of_revenue_from_other_operating_cost(rows)

        assert rows[0]["cost_of_goods_and_services_sold"] == 115.0

    def test_does_not_fire_when_excise_tax_absent(self) -> None:
        rows = [{"cost_of_goods_and_services_sold": 6_866_200_000.0}]

        _fill_cost_of_revenue_from_other_operating_cost(rows)

        assert rows[0]["cost_of_goods_and_services_sold"] == 6_866_200_000.0

    def test_pm_style_excise_tax_addition_validated_out(self) -> None:
        """FIXED 2026-09-07 (gross_profit_identity live tie-out follow-up): PM (Philip Morris,
        CIK 0001413329) FY2025 tags BOTH CostOfGoodsAndServicesSold ($13.366B) and
        ExciseAndSalesTaxes ($53.211B), same shape as TAP - but unlike TAP, PM's own tagged
        GrossProfit ($27.282B) ALREADY reconciles with COGS alone (revenue $40.648B - COGS
        $13.366B = $27.282B, exact). Adding excise tax on top (as the old unconditional
        behavior did) produced cost_of_revenue=$66.577B, exceeding revenue entirely. Must be
        validated out here, not summed in blindly."""
        rows = [
            {
                "revenue_from_contract_with_customer_excluding_assessed_tax": 40_648_000_000.0,
                "cost_of_goods_and_services_sold": 13_366_000_000.0,
                "excise_and_sales_taxes": 53_211_000_000.0,
                "gross_profit": 27_282_000_000.0,
            }
        ]

        _fill_cost_of_revenue_from_other_operating_cost(rows)

        assert rows[0]["cost_of_goods_and_services_sold"] == 13_366_000_000.0
        assert "excise_and_sales_taxes" not in rows[0]
