"""Regression test for the 2026-08-11 fix: two data_patrol checks
(CoverageChecker.check_loader_coverage's critical_tables list, and
AlignmentChecker's cross-table alignment checks list) applied a universal
percent-of-active-universe coverage threshold (96-98% / 95%) to signal_quality_scores, a
table that is sparse BY DESIGN - only symbols that qualify get a row, confirmed stable at
~10.5% of the universe (512-2510/4945 symbols) across 12 recent trading days, not an
anomaly. This is the same bug class as the buy_sell_daily fix in the same commit series
(test_data_patrol_buy_sell_daily_sparse_by_design.py) and made both checks unconditional,
permanent false alarms every single day. signal_quality_scores is now validated via its own
dedicated absolute-row-count contract (patrol_signal_quality_scores_14d_min), so removing it
from these two universal-baseline checks doesn't reduce real coverage validation.
"""

import inspect

from algo.infrastructure.config.main import AlgoConfig
from algo.monitoring.data_patrol.checks.alignment import AlignmentChecker
from algo.monitoring.data_patrol.checks.coverage import CoverageChecker


class TestSignalQualityScoresSparseByDesign:
    def test_coverage_checker_critical_tables_excludes_signal_quality_scores(self):
        source = inspect.getsource(CoverageChecker.check_loader_coverage)
        list_start = source.index("critical_tables = [")
        list_end = source.index("]", list_start)
        critical_tables_literal = source[list_start:list_end]

        assert '"signal_quality_scores"' not in critical_tables_literal, (
            "signal_quality_scores must not be in critical_tables - it's sparse by design "
            "and already validated via its own dedicated loader_contract "
            "(patrol_signal_quality_scores_14d_min)"
        )
        # Sanity: the fix shouldn't have accidentally removed a genuinely near-universal table
        assert '"price_daily"' in critical_tables_literal
        assert '"technical_data_daily"' in critical_tables_literal

    def test_alignment_checker_cross_align_excludes_signal_quality_scores_ratio_check(self):
        source = inspect.getsource(AlignmentChecker)
        checks_start = source.index('checks = [\n            (\n                "technical_data_daily"')
        checks_end = source.index("]\n\n        try:", checks_start)
        checks_literal = source[checks_start:checks_end]

        assert '"signal_quality_scores"' not in checks_literal, (
            "signal_quality_scores must not have a percent-of-universe ratio check in "
            "cross_align - same sparse-by-design reasoning as the buy_sell_daily fix"
        )
        # Sanity: other genuinely near-universal tables must still be checked
        assert '"technical_data_daily"' in checks_literal

    def test_loader_contract_defines_signal_quality_scores(self):
        contracts = AlgoConfig().data_patrol.get_loader_contracts()
        assert "signal_quality_scores" in contracts
        contract = contracts["signal_quality_scores"]
        assert contract["min_rows"] > 0
        assert contract["severity"] == "error"
