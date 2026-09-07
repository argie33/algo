"""Regression test for the 2026-09-07 fix (goal session: stock_scores factor audit + tie-out
CI sweep, gross_profit_identity live triage): Tetra Tech (TTEK, CIK 0000831641, $5.44B FY2025
revenue environmental/engineering consulting firm) tags real subcontractor/pass-through project
costs under "OtherCostOfOperatingRevenue" ($3,656,016,000 FY2025) SEPARATE from its main
"CostOfGoodsAndServicesSold" ($825,230,000) - live-confirmed via real SEC companyfacts JSON:
only their SUM ($4,481,246,000) reconciles with TTEK's own filed GrossProfit ($961,344,000 =
$5,442,590,000 revenue - $4,481,246,000, exact to the dollar).
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
