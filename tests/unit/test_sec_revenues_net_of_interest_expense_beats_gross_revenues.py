"""Regression test for a magnitude-resolution bug found during the 2026-09-13 /goal
scoring-accuracy audit while investigating a yfinance-crosscheck WARN on an unrelated
symbol (SCM) - digging into the DQC/Arelle "zero impact on us" AMP finding surfaced a
real, separate revenue bug rather than confirming there was nothing to find.

Live-confirmed via AMP's (Ameriprise Financial) own FY2025 10-K calculation linkbase
(CONSOLIDATEDSTATEMENTSOFOPERATIONS role): "RevenuesNetOfInterestExpense" is declared as
Revenues - InterestExpenseDeposits ($18,480,000,000 = $18,911,000,000 - $431,000,000) -
i.e. "Revenues" is a GROSS SUB-LINE of the real bottom-line total for this filer, not an
alternative/larger total. sec_base.py's `_REVENUE_TOTAL_CANDIDATE_FIELDS` magnitude
resolution ("whichever candidate has the largest positive value wins") assumes the
opposite - "a real consolidated total can never be smaller than a genuine sub-line of
itself" - which is exactly backwards for this pair, so it was picking the larger-but-wrong
"Revenues" figure. SF (Stifel Financial) independently confirmed the identical shape via
its own real SEC companyfacts JSON ($6,347,533,000 Revenues vs $5,529,730,000
RevenuesNetOfInterestExpense, and our own annual_income_statement.revenue for SF was
confirmed live-stored as the wrong, larger figure before this fix).

Checked this isn't a blanket assumption: PRU/LNC/VOYA/UNM/PFG (5 other diversified
insurers/financials) never tag RevenuesNetOfInterestExpense at all, and MS/WFC (the
original 2026-08-01 fix's target filers) only tag RevenuesNetOfInterestExpense with
"Revenues" silent - no conflict for either group. The bug only fires for filers (AMP, SF -
both have a deposit-taking/banking subsidiary alongside their core business) that report
BOTH concepts as real, non-zero values for the same period.

Fix: revenues_net_of_interest_expense now gets unconditional priority over plain
"revenues" within the magnitude group, tracked via a new `revenue_total_source` dict so
the override applies regardless of which field is processed first. Every other pair in
_REVENUE_TOTAL_CANDIDATE_FIELDS (sales_revenue_net/regulated_operating_revenue/etc.) keeps
the existing pure-magnitude rule - see
test_sec_sales_revenue_net_magnitude_resolves_over_small_revenues.py, unaffected.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader


class TestRevenuesNetOfInterestExpenseBeatsGrossRevenues:
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

    def test_amp_2025_net_total_wins_despite_smaller_magnitude(self):
        loader = self._make_loader()
        row = {
            "symbol": "AMP",
            "fiscal_year": 2025,
            "revenues": 18_911_000_000.0,
            "revenues_net_of_interest_expense": 18_480_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["revenue"] == 18_480_000_000.0

    def test_sf_2025_net_total_wins_despite_smaller_magnitude(self):
        loader = self._make_loader()
        row = {
            "symbol": "SF",
            "fiscal_year": 2025,
            "revenues": 6_347_533_000.0,
            "revenues_net_of_interest_expense": 5_529_730_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["revenue"] == 5_529_730_000.0

    def test_order_independent_revenues_net_processed_first(self):
        """Same result regardless of dict insertion order - the override must not depend
        on which field the aggregation loop happens to see first."""
        loader = self._make_loader()
        row = {
            "symbol": "AMP",
            "fiscal_year": 2025,
            "revenues_net_of_interest_expense": 18_480_000_000.0,
            "revenues": 18_911_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["revenue"] == 18_480_000_000.0

    def test_ms_style_revenues_net_only_still_works(self):
        """MS/WFC-style filers (only RevenuesNetOfInterestExpense reported, "Revenues"
        silent/absent) must be unaffected by this change - no conflict to resolve."""
        loader = self._make_loader()
        row = {
            "symbol": "MS",
            "fiscal_year": 2025,
            "revenues_net_of_interest_expense": 70_645_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["revenue"] == 70_645_000_000.0
