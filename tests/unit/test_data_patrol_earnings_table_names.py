"""Regression test for the 2026-08-11 fix: SpecializedChecker.check_earnings_data()
referenced two table names that were never real.

"earnings_estimates" has never existed - the actual forward-EPS estimates writer
(loaders/load_analyst_earnings_estimates.py) writes to analyst_earnings_estimates,
confirmed live against information_schema.tables (this check had been silently
ERROR-logging "relation does not exist" every single run since it was written).

"earnings_estimate_revisions" has never existed anywhere in this codebase (grep-confirmed
no loader, migration, or other code references a table by that name) - revision data
(estimate_revision_direction) is computed inline from analyst_earnings_estimates by
load_enhanced_quality_growth_metrics.py, never persisted to its own table. Removed
entirely rather than renamed, since monitoring a table that was never built provides
zero signal.

"earnings_history" is loader_registry.py's own documented "permanently-empty legacy
table" - nothing writes to it. The loader that actually runs (load_earnings_calendar_sec.py)
writes to earnings_calendar_sec (353k+ rows, updated daily). Live-confirmed via
`python -m algo.algo_data_patrol --quick --json`: before this fix, the overall patrol
readiness gate reported ready=False due to these guaranteed-failing earnings checks;
after, it reports ready=True with real data (analyst_earnings_estimates: 38,617 rows,
99.8% symbol coverage; earnings_calendar_sec: fresh same-day).
"""

import inspect

from algo.monitoring.data_patrol.checks.specialized import SpecializedChecker


class TestEarningsCheckTableNames:
    def test_sources_list_uses_real_tables_only(self):
        source = inspect.getsource(SpecializedChecker.check_earnings_data)
        list_start = source.index("sources = [")
        list_end = source.index("for tbl, col_options", list_start)
        sources_literal = source[list_start:list_end]

        assert '"earnings_estimates"' not in sources_literal, (
            "earnings_estimates has never been a real table - the real writer targets analyst_earnings_estimates"
        )
        assert '"earnings_estimate_revisions"' not in sources_literal, (
            "earnings_estimate_revisions has never existed anywhere in this codebase - "
            "revision data is computed inline, never persisted to its own table"
        )
        assert '"earnings_history"' not in sources_literal, (
            "earnings_history is loader_registry.py's documented permanently-empty legacy "
            "table - the real, actively-updated table is earnings_calendar_sec"
        )
        assert '"analyst_earnings_estimates"' in sources_literal
        assert '"earnings_calendar_sec"' in sources_literal

    def test_coverage_query_joins_the_real_estimates_table(self):
        source = inspect.getsource(SpecializedChecker.check_earnings_data)
        assert "LEFT JOIN earnings_estimates e" not in source, (
            "the coverage query's JOIN must also target the real table, not the never-existed earnings_estimates"
        )
        assert "LEFT JOIN analyst_earnings_estimates e" in source
