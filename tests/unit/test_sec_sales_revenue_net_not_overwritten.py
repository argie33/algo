"""Regression test for the goods-revenue-sub-line bug found live 2026-08-09 investigating
KARO (Karooooo/Cartrack, a pure IFRS 20-F filer): its real total revenue is reported
under the IFRS "Revenue" concept (aliased to "revenues", ZAR 4,567,459,000 for FY2025 -
built from subscription/transport/goods sub-lines), but it also separately tags just the
goods-sold sub-line under "RevenueFromSaleOfGoods" (aliased to "sales_revenue_net", ZAR
37,018,000 - ~1% of total revenue). loaders/helpers/sec_base.py::transform()'s general
priority chain (last-listed concept wins on overwrite) let the much smaller goods-only
figure silently overwrite the real total, producing >1000% margin/ratio garbage
downstream (operating_margin, net_margin, gross_margin, dividend_yield, ev_revenue, etc.
all divide by this corrupted revenue).

"sales_revenue_net" is also the target key for us-gaap "SalesRevenueNet" (a genuine total
net-sales concept some legacy/pre-ASC-606 filers use as their PRIMARY revenue tag - see
the AGCO fix on "sales_revenue_goods_net"), so the fix can't just remove the concept: it
must only stop clobbering when a real total is already present, same "fallback only"
mechanism already used for interest_income_operating/interest_and_dividend_income_operating.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader


class TestSalesRevenueNetNotOverwritingRealTotalRevenue:
    def _make_loader(self):
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_income_statement"
        loader.period = "annual"
        loader.statement_type = "income"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "revenue", "data_unavailable", "reason"})
        loader._field_mapping = {
            "revenues": "revenue",
            "sales_revenue_net": "revenue",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset({"sales_revenue_net"})
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        return loader

    def test_real_total_revenue_not_overwritten_by_goods_only_sub_line(self):
        loader = self._make_loader()
        row = {
            "symbol": "KARO",
            "fiscal_year": 2025,
            "revenues": 4_567_459_000.0,
            "sales_revenue_net": 37_018_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["revenue"] == 4_567_459_000.0

    def test_sales_revenue_net_still_wins_when_no_total_revenue_present(self):
        # Legacy pre-ASC-606 us-gaap filer (e.g. AGCO-style): SalesRevenueNet is the
        # only revenue tag reported at all, so it must still populate "revenue" normally.
        loader = self._make_loader()
        row = {
            "symbol": "OLDCO",
            "fiscal_year": 2010,
            "sales_revenue_net": 6_520_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["revenue"] == 6_520_000_000.0
