"""Regression test for the 2026-08-11 fix: SpecializedChecker.check_earnings_data()
queried "earnings_estimates" and "earnings_estimate_revisions", neither of which has ever
existed as a real table (confirmed against information_schema.tables) - a guaranteed
DatabaseError on every single run. The real forward-EPS table is
"analyst_earnings_estimates" (written by load_analyst_earnings_estimates.py, 38k+ rows).
Also verifies the per-source SAVEPOINT was added so one source's failure can't abort the
whole checker's transaction for every subsequent source/check.
"""

import inspect

from algo.monitoring.data_patrol.checks.specialized import SpecializedChecker


class TestEarningsEstimatesNonexistentTable:
    def test_check_earnings_data_uses_real_table_name(self):
        source = inspect.getsource(SpecializedChecker.check_earnings_data)
        list_start = source.index("sources = [")
        list_end = source.index("]", list_start)
        sources_literal = source[list_start:list_end]

        assert '"earnings_estimates"' not in sources_literal, (
            "earnings_estimates has never been a real table - querying it guarantees a DatabaseError on every run"
        )
        assert '"earnings_estimate_revisions"' not in sources_literal, (
            "earnings_estimate_revisions has never been a real table - no loader or migration has ever created it"
        )
        assert '"analyst_earnings_estimates"' in sources_literal, (
            "the real forward-EPS table (analyst_earnings_estimates) must still be checked"
        )

    def test_check_earnings_data_uses_savepoint_isolation(self):
        source = inspect.getsource(SpecializedChecker.check_earnings_data)
        assert "SAVEPOINT" in source, (
            "each source must roll back to its own savepoint on failure so a bad table name "
            "doesn't abort the transaction for every subsequent source/check"
        )
