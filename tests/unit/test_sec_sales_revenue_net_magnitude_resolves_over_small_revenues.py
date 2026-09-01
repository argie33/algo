"""Regression test for the reverse of test_sec_sales_revenue_net_not_overwritten.py's KARO
case, found during the 2026-08-31 goal session ("get all the data we need" full-coverage
audit) while investigating a DB-wide "cost_of_revenue >> revenue" scan.

Live-confirmed via real SEC companyconcept JSON: ANDE (Andersons, SIC 5153, grain/
agribusiness) tags "Revenues" for FY2013-2015 with a small, wrong sub-line figure
($882,000/$6,159,000/$5,447,000) while "SalesRevenueNet" correctly holds the real total
for those same years ($5,604,574,000/$4,540,071,000/$4,198,495,000). Because "revenues" is
a magnitude-candidate field (sec_base.py's _REVENUE_TOTAL_CANDIDATE_FIELDS) that wins
"revenue" first, and "sales_revenue_net" was previously fallback-only (never overwrites an
already-populated value), the wrong small figure was permanently locked in - no
data_unavailable/reason flag anywhere. PRGO (Perrigo, SIC 2834) independently confirmed
the identical shape for FY2013: real "Revenues"=$800,000 vs real
"SalesRevenueGoodsNet"/"SalesRevenueNet"=$3,539,800,000.

This exact fix (moving both fields into the magnitude-resolved group) was written and
live-verified once already this session on an isolated worktree branch
(`worktree-growth-multi-input-blend`, commit d175737e3) but never actually reached main -
`git merge-base --is-ancestor d175737e3 HEAD` returned false. Discovered while triaging TKR
(Timken) from the same revenue-collision scan and finding main's
_REVENUE_TOTAL_CANDIDATE_FIELDS still lacked these two fields despite memory citing this as
FIXED. Re-verified ANDE/PRGO's real figures are unchanged before porting.

NOTE: TKR turned out NOT to be an instance of this mechanism, despite an initial hypothesis
otherwise - live-checked the DB directly (not just the SEC data) and found TKR's other
fiscal years (2013, 2014) already correctly resolve to their real SalesRevenueGoodsNet
annual totals, so no competing "revenues" tag is winning first for this symbol. FY2015's
wrong $20,600,000 is a stray SalesRevenueGoodsNet fact itself, tagged against a
non-standard 2014-10-01/2015-09-30 comparative period rather than the real annual
2015-01-01/2015-12-31 period ($2,872,300,000) - a duration-fact PERIOD-selection bug, the
same class already partially fixed for JAKK (0a48b91c3) but evidently not covering this
exact shape. Left unfixed here - see the sec_valuations/data-quality follow-up memory note
for TKR instead of assuming this commit resolves it.

Fix: sales_revenue_net/sales_revenue_goods_net moved into the magnitude-resolved
_REVENUE_TOTAL_CANDIDATE_FIELDS group - whichever total-candidate concept has the LARGEST
value now wins "revenue", regardless of processing order, while the existing seed-from-
already-populated-row step still protects a real, larger, already-written total from a
smaller candidate (verified via the existing KARO/OLDCO tests, unchanged by this fix).
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader


class TestSalesRevenueNetMagnitudeResolvesOverSmallRevenues:
    def _make_loader(self):
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_income_statement"
        loader.period = "annual"
        loader.statement_type = "income"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "revenue", "data_unavailable", "reason"})
        loader._field_mapping = {
            "revenues": "revenue",
            "sales_revenue_net": "revenue",
            "sales_revenue_goods_net": "revenue",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset({"sales_revenue_net", "sales_revenue_goods_net"})
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        return loader

    def test_ande_2013_real_total_wins_over_small_wrong_revenues_tag(self):
        loader = self._make_loader()
        row = {
            "symbol": "ANDE",
            "fiscal_year": 2013,
            "revenues": 882_000.0,
            "sales_revenue_net": 5_604_574_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["revenue"] == 5_604_574_000.0

    def test_prgo_2013_real_total_wins_over_small_wrong_revenues_tag(self):
        loader = self._make_loader()
        row = {
            "symbol": "PRGO",
            "fiscal_year": 2013,
            "revenues": 800_000.0,
            "sales_revenue_goods_net": 3_539_800_000.0,
            "sales_revenue_net": 3_539_800_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["revenue"] == 3_539_800_000.0

    def test_real_total_still_not_overwritten_by_goods_only_sub_line(self):
        """KARO case still protected: a much-larger real total already written from
        "revenues" must not be clobbered by a smaller sales_revenue_net candidate."""
        loader = self._make_loader()
        row = {
            "symbol": "KARO",
            "fiscal_year": 2025,
            "revenues": 4_567_459_000.0,
            "sales_revenue_net": 37_018_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["revenue"] == 4_567_459_000.0
