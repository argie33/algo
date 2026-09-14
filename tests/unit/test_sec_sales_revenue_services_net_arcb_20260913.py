"""Regression test for a missing-concept-mapping bug found during the 2026-09-13
quarantine-backlog empirical-verification pass (same bug class as
test_sec_sales_revenue_net_magnitude_resolves_over_small_revenues.py's AGCO/ANDE/PRGO cases -
a legitimate total-revenue concept was never mapped at all, letting a tiny unrelated fallback
concept win "revenue" by default).

Live-confirmed via ARCB (ArcBest Corporation, SIC 4213 trucking/logistics): real annual
revenue is tagged under "SalesRevenueServicesNet" ($1.9076B/$2.066B/$2.2995B for FY2011-2013,
matching the sum of ARCB's own real, discrete, promptly-filed quarterly "Revenues" facts) -
ARCB never tags "Revenues" or "SalesRevenueNet" at the annual level at all. Before this fix,
"SalesRevenueServicesNet" wasn't mapped to any field, so it was silently discarded, and a
tiny, unrelated "InvestmentIncomeInterestAndDividend" fact ($1,069,000 FY2011) won "revenue"
by default via the mortgage-REIT/community-bank fallback-of-last-resort mechanism - a
~1,785x understatement, feeding ARCB into the quarterly_revenue_sum_vs_annual_extreme
DataPatrol quarantine.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader


class TestSalesRevenueServicesNetArcb:
    def _make_loader(self):
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_income_statement"
        loader.period = "annual"
        loader.statement_type = "income"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "revenue", "data_unavailable", "reason"})
        loader._field_mapping = {
            "sales_revenue_services_net": "revenue",
            "investment_income_interest_and_dividend": "revenue",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset({"investment_income_interest_and_dividend"})
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        return loader

    def test_arcb_2011_real_total_wins_over_tiny_investment_income_fallback(self):
        loader = self._make_loader()
        row = {
            "symbol": "ARCB",
            "fiscal_year": 2011,
            "sales_revenue_services_net": 1_907_609_000.0,
            "investment_income_interest_and_dividend": 1_069_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["revenue"] == 1_907_609_000.0

    def test_arcb_2011_order_independent(self):
        loader = self._make_loader()
        row = {
            "symbol": "ARCB",
            "fiscal_year": 2011,
            "investment_income_interest_and_dividend": 1_069_000.0,
            "sales_revenue_services_net": 1_907_609_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["revenue"] == 1_907_609_000.0
