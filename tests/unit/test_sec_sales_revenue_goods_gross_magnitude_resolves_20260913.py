"""Regression test: "sales_revenue_goods_gross" added to the magnitude-resolved
_REVENUE_TOTAL_CANDIDATE_FIELDS group (goal session: "patrols and checks"/quarantine-
backlog audit).

MGPI (MGP Ingredients, SIC 2085): FY2013/2014 10-Ks tag "Revenues" with a small, wrong
sub-line ($12,665,000/$16,306,000 - a royalty/JV distribution line, not a revenue total)
while "SalesRevenueGoodsGross" correctly holds the real total for FY2014
($338,352,000, matching the sum of MGPI's own real discrete quarterly revenue) - the
filer switched to "SalesRevenueNet" starting its FY2015 filing, leaving FY2013/2014 with
no concept previously mapped at all besides the small, wrong "Revenues" tag. Same bug
class as the existing ANDE/PRGO/TKR sales_revenue_net magnitude-resolution precedent,
"SalesRevenueGoodsGross" concept instead.

Fix: "sales_revenue_goods_gross" added to sec_base.py's _REVENUE_TOTAL_CANDIDATE_FIELDS -
whichever total-candidate concept has the LARGEST value wins "revenue", same mechanism as
the existing sales_revenue_net/regulated_operating_revenue/utility_revenue entries in that
group.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader


class TestSalesRevenueGoodsGrossMagnitudeResolves:
    def _make_loader(self):
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_income_statement"
        loader.period = "annual"
        loader.statement_type = "income"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "revenue", "data_unavailable", "reason"})
        loader._field_mapping = {
            "revenues": "revenue",
            "sales_revenue_goods_gross": "revenue",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset()
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        return loader

    def test_mgpi_2014_real_total_wins_over_small_wrong_revenues_tag(self):
        loader = self._make_loader()
        row = {
            "symbol": "MGPI",
            "fiscal_year": 2014,
            "revenues": 16_306_000.0,
            "sales_revenue_goods_gross": 338_352_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["revenue"] == 338_352_000.0
