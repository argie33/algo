"""Regression test for the 2026-09-13 /goal quarantine-backlog audit fix: the AMP/SF
"revenues_net_of_interest_expense beats gross revenues unconditionally" override
(test_sec_revenues_net_of_interest_expense_beats_gross_revenues.py) was too broad and let a
filer-side XBRL tagging error win.

Live-confirmed via AMZE's real SEC companyfacts JSON: FY2022 real "Revenues" = $2,860,001
(exactly equal to the sum of AMZE's own quarterly revenue facts), but the filer also tags
"RevenuesNetOfInterestExpense" = $13,750 for the same period - a stray value shared with
several unrelated mistagged concepts in the same filing (DeferredRevenueRevenueRecognized1,
IncreaseDecreaseInDeferredRevenue, ContractWithCustomerLiabilityRevenueRecognized), not a
real net-of-interest-expense total. This fed AMZE into the
quarterly_revenue_sum_vs_annual_extreme DataPatrol quarantine ("the annual revenue figure
itself is likely broken").
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader


class TestRevenuesNetOfInterestExpenseImplausibleRatioRejected:
    def _make_loader(self):
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_income_statement"
        loader.period = "annual"
        loader.statement_type = "income"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "revenue", "data_unavailable", "reason"})
        loader._field_mapping = {
            "revenues": "revenue",
            "revenues_net_of_interest_expense": "revenue",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset()
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        return loader

    def test_amze_2022_garbage_net_tag_does_not_clobber_real_gross_revenue(self):
        loader = self._make_loader()
        row = {
            "symbol": "AMZE",
            "fiscal_year": 2022,
            "revenues": 2_860_001.0,
            "revenues_net_of_interest_expense": 13_750.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["revenue"] == 2_860_001.0

    def test_amze_2022_order_independent(self):
        loader = self._make_loader()
        row = {
            "symbol": "AMZE",
            "fiscal_year": 2022,
            "revenues_net_of_interest_expense": 13_750.0,
            "revenues": 2_860_001.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["revenue"] == 2_860_001.0

    def test_amp_2025_genuine_net_total_still_wins(self):
        """Plausibility gate must not regress the original AMP/SF fix."""
        loader = self._make_loader()
        row = {
            "symbol": "AMP",
            "fiscal_year": 2025,
            "revenues": 18_911_000_000.0,
            "revenues_net_of_interest_expense": 18_480_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["revenue"] == 18_480_000_000.0

    def test_sf_2025_genuine_net_total_still_wins(self):
        loader = self._make_loader()
        row = {
            "symbol": "SF",
            "fiscal_year": 2025,
            "revenues": 6_347_533_000.0,
            "revenues_net_of_interest_expense": 5_529_730_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["revenue"] == 5_529_730_000.0
