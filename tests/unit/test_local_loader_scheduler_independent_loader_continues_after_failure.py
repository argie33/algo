"""Regression: one loader's failure must not abort unrelated downstream loaders in the
same pipeline.

BUG FOUND 2026-08-10 (live-reproduced): run_pipeline() returned 1 immediately on any
loader's non-zero exit code or timeout, aborting the entire rest of the pipeline -
including loaders with zero declared dependency on the one that failed.
LOADER_DEPENDENCIES only lists 3 real dependency edges (value_quality_growth,
enhanced_quality_growth, segment_metrics); "buy_sell" isn't in it at all, yet a "scores"
failure (its own upstream-coverage data-quality gate, an expected/legitimate failure mode,
not a crash) permanently blocked "buy_sell" from ever being attempted in the same
--now signals run. This is the root cause of buy_sell_daily's session-long staleness.

Fixed: skip only the failed loader and anything that genuinely depends on it (still
enforced via _check_loader_dependencies), not the whole remaining pipeline. Overall exit
code is still 1 if anything failed, preserving the "something went wrong" signal.
"""

import importlib.util
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_scheduler_module():
    spec = importlib.util.spec_from_file_location(
        "local_loader_scheduler_under_test", REPO_ROOT / "scripts" / "local_loader_scheduler.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestIndependentLoaderContinuesAfterUpstreamFailure:
    def test_second_independent_loader_still_runs_after_first_fails(self):
        module = _load_scheduler_module()
        # "trend_analysis" and "sector_industry" have no LOADER_DEPENDENCIES entry between
        # them (neither declares a dependency on the other) - a real independent pair,
        # matching the real "scores" -> "buy_sell" case without depending on that exact
        # pipeline's current membership.
        results = [MagicMock(returncode=1), MagicMock(returncode=0)]
        with patch.object(module, "PIPELINES", {"test_pipeline": ["trend_analysis", "sector_industry"]}), \
             patch.object(module, "reap_stale_running_loaders", return_value=[]), \
             patch.object(module.subprocess, "run", side_effect=results) as mock_run, \
             patch.object(module, "_mark_loader_failed_after_crash") as mock_mark:
            rc = module.run_pipeline("test_pipeline")

        # Both loaders were actually invoked - the second was not skipped.
        assert mock_run.call_count == 2
        # Overall pipeline still reports failure (something did go wrong).
        assert rc == 1
        # Only the first (failed) loader got marked failed.
        mock_mark.assert_called_once()
        assert mock_mark.call_args.args[0] == "load_trend_analysis.py"

    def test_dependent_loader_is_still_skipped_after_its_real_dependency_fails(self):
        module = _load_scheduler_module()
        # Isolate from LOADER_DEPENDENCIES' real chains (value_quality_growth itself
        # requires financial_statements/valuations/analyst_earnings_estimates, which would
        # skip it before it even runs) - use a synthetic 2-loader dependency edge instead.
        mock_result = MagicMock(returncode=1)
        with patch.object(module, "PIPELINES", {"test_pipeline": ["trend_analysis", "sector_industry"]}), \
             patch.object(module, "LOADER_DEPENDENCIES", {"sector_industry": ["trend_analysis"]}), \
             patch.object(module, "reap_stale_running_loaders", return_value=[]), \
             patch.object(module.subprocess, "run", return_value=mock_result) as mock_run, \
             patch.object(module, "_mark_loader_failed_after_crash"):
            rc = module.run_pipeline("test_pipeline")

        # Only the first loader (trend_analysis) was actually invoked and failed -
        # sector_industry, which genuinely depends on it, was correctly skipped.
        assert mock_run.call_count == 1
        assert rc == 1

    def test_all_success_still_returns_zero(self):
        module = _load_scheduler_module()
        mock_result = MagicMock(returncode=0)
        with patch.object(module, "PIPELINES", {"test_pipeline": ["trend_analysis", "sector_industry"]}), \
             patch.object(module, "reap_stale_running_loaders", return_value=[]), \
             patch.object(module.subprocess, "run", return_value=mock_result) as mock_run:
            rc = module.run_pipeline("test_pipeline")

        assert mock_run.call_count == 2
        assert rc == 0
