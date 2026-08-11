"""Regression test for the 2026-08-11 fix: two data_patrol checks
(CoverageChecker.check_loader_coverage's critical_tables list, and
AlignmentChecker's cross-table alignment checks list) applied a universal
percent-of-active-universe coverage threshold (96-98% / 90%) to buy_sell_daily, a table
that is sparse BY DESIGN - only symbols that actually get a buy/sell classification get a
row, confirmed stable at ~18-20% of the universe (895-1008/4945 symbols) across 6
consecutive real trading days, not an anomaly. This made both checks unconditional, permanent
false alarms every single day. buy_sell_daily is already correctly validated elsewhere via
its own dedicated absolute-row-count contract (patrol_buy_sell_daily_14d_min), so removing it
from these two universal-baseline checks doesn't reduce real coverage validation.
"""

import inspect

from algo.monitoring.data_patrol.checks.alignment import AlignmentChecker
from algo.monitoring.data_patrol.checks.coverage import CoverageChecker


class TestBuySellDailySparseByDesign:
    def test_coverage_checker_critical_tables_excludes_buy_sell_daily(self):
        source = inspect.getsource(CoverageChecker.check_loader_coverage)
        list_start = source.index("critical_tables = [")
        list_end = source.index("]", list_start)
        critical_tables_literal = source[list_start:list_end]

        assert '"buy_sell_daily"' not in critical_tables_literal, (
            "buy_sell_daily must not be in critical_tables - it's sparse by design and "
            "already validated via its own dedicated loader_contract "
            "(patrol_buy_sell_daily_14d_min)"
        )
        # Sanity: the fix shouldn't have accidentally removed a genuinely near-universal table
        assert '"price_daily"' in critical_tables_literal
        assert '"technical_data_daily"' in critical_tables_literal

    def test_alignment_checker_cross_align_excludes_buy_sell_daily_ratio_check(self):
        source = inspect.getsource(AlignmentChecker)
        checks_start = source.index('checks = [\n            (\n                "technical_data_daily"')
        checks_end = source.index("]\n\n        try:", checks_start)
        checks_literal = source[checks_start:checks_end]

        assert '"buy_sell_daily"' not in checks_literal, (
            "buy_sell_daily must not have a percent-of-universe ratio check in cross_align - "
            "same sparse-by-design reasoning as the coverage.py fix"
        )
        # Sanity: other genuinely near-universal tables must still be checked
        assert '"technical_data_daily"' in checks_literal
