"""Regression test for a third instance of the sales_revenue_net-shaped bug (see
test_sec_sales_revenue_net_magnitude_resolves_over_small_revenues.py), found during the
2026-08-31 goal session ("get all the data we need" full-coverage audit) while spot-checking
more rows from the same DB-wide "cost_of_revenue >> revenue" scan.

regulated_operating_revenue/regulated_and_unregulated_operating_revenue were designed for
"pure single-segment regulated utility with no unregulated business" filers
(get_income_statement()'s own RegulatedOperatingRevenue comment), where they're temporally
exclusive with "Revenues" - safe under plain last-processed-wins because only one is ever
populated for a given fiscal year. Live-confirmed via ALTO (Alto Ingredients, an ethanol
producer, SIC 2860, NOT a utility): real, complete "Revenues"=$1,222,940,000 for FY2023
coexists with an unrelated minor RegulatedOperatingRevenue fact ($3,216,500, some regulated
commodity-credit line) for the SAME year - the temporal-exclusivity assumption doesn't hold,
and the smaller concept (listed after "Revenues" in the concepts list) was unconditionally
winning "revenue" via plain last-processed-wins.

Fix: moved both into the magnitude-resolved _REVENUE_TOTAL_CANDIDATE_FIELDS group -
whichever total-candidate concept has the LARGEST value wins "revenue" regardless of
processing order. Verified this doesn't regress the existing XEL/OGS utility-recovery
precedent (test_sec_utility_revenue_concept_fallback.py) - those cases only ever have ONE
candidate populated per fiscal year, so magnitude resolution is a no-op there.
"""

from loaders.helpers.sec_base import SecEdgarStatementLoader


class TestRegulatedOperatingRevenueMagnitudeResolves:
    def _make_loader(self):
        loader = SecEdgarStatementLoader.__new__(SecEdgarStatementLoader)
        loader.table_name = "annual_income_statement"
        loader.period = "annual"
        loader.statement_type = "income"
        loader._schema_cols = frozenset({"symbol", "fiscal_year", "revenue", "data_unavailable", "reason"})
        loader._field_mapping = {
            "revenues": "revenue",
            "regulated_operating_revenue": "revenue",
            "regulated_and_unregulated_operating_revenue": "revenue",
            "data_unavailable": "data_unavailable",
            "reason": "reason",
        }
        loader._fallback_only_fields = frozenset()
        loader._reit_only_fallback_fields = frozenset()
        loader._reit_symbols = frozenset()
        return loader

    def test_alto_2023_real_total_wins_over_small_regulated_revenue_subline(self):
        loader = self._make_loader()
        row = {
            "symbol": "ALTO",
            "fiscal_year": 2023,
            "revenues": 1_222_940_000.0,
            "regulated_operating_revenue": 3_216_500.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["revenue"] == 1_222_940_000.0

    def test_utility_still_recovered_when_only_candidate_present(self):
        """XEL/OGS-style case still works: regulated_and_unregulated_operating_revenue is
        the ONLY candidate present (Revenues went silent for this filer/year), so it must
        still populate "revenue" normally."""
        loader = self._make_loader()
        row = {
            "symbol": "XEL",
            "fiscal_year": 2025,
            "regulated_and_unregulated_operating_revenue": 14_669_000_000.0,
        }

        transformed = loader.transform([row])

        assert transformed[0]["revenue"] == 14_669_000_000.0
