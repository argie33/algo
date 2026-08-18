"""Regression test for the pure-play IFRS gold-miner revenue gap found live 2026-08-18
(goal: "no SEC data"/loader audit, Loews dashboard screenshot investigation).

B2Gold (BTG, CIK 1429937) live-confirmed via real companyfacts JSON: files exclusively
under the ifrs-full namespace (no us-gaap facts at all) and never tags "Revenue" or any
other concept in _INCOME_IFRS_ALIASES - its only revenue-bearing concepts are
"RevenueFromSaleOfGold" and "RevenueFromSaleOfSilver" (a minor byproduct credit), summed
nowhere in a single non-dimensional total. Before this fix, annual_income_statement.revenue
was NULL for BTG despite 9+ years of real net_income data, mislabeling a real extraction
gap as "missing_sec_data". Mapping RevenueFromSaleOfGold alone (gold is the overwhelming
majority of revenue for these filers) recovers most of the real figure - same "partial but
far better than missing" precedent as sales_revenue_goods_net's existing AGCO/goods-line
use, and the same fallback-only mechanism (see _REVENUE_FALLBACK_ONLY_FIELDS) as
test_sec_sales_revenue_net_not_overwritten.py's KARO case ensures it never clobbers a real
total revenue figure for filers that report one.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader


class TestGoldRevenueFallback:
    def _make_loader(self):
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_income_statement"
        loader.period = "annual"
        loader.statement_type = "income"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "revenue", "data_unavailable", "reason"})
        loader._field_mapping = {
            "revenues": "revenue",
            "sales_revenue_goods_net": "revenue",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset({"sales_revenue_goods_net"})
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        return loader

    def test_gold_revenue_populates_revenue_when_nothing_else_present(self):
        loader = self._make_loader()
        row = {
            "symbol": "BTG",
            "fiscal_year": 2025,
            "sales_revenue_goods_net": 1_850_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["revenue"] == 1_850_000_000.0

    def test_gold_revenue_does_not_overwrite_real_total_revenue(self):
        loader = self._make_loader()
        row = {
            "symbol": "SOMECO",
            "fiscal_year": 2025,
            "revenues": 2_000_000_000.0,
            "sales_revenue_goods_net": 1_850_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["revenue"] == 2_000_000_000.0
