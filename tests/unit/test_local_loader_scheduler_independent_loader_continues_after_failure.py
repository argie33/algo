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
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_scheduler_module(tmp_path):
    """Load the real scheduler source from a copy under tmp_path, not its real repo location -
    see test_local_loader_scheduler_marks_failed_on_crash.py's _load_scheduler_module for why
    (these tests use "trend_analysis"/"sector_industry" with real, unmocked wall-clock
    timestamps, so loading straight from the real file leaks real logs/load_*_<epoch>.log
    files on every run)."""
    fake_scripts_dir = tmp_path / "scripts"
    fake_scripts_dir.mkdir(parents=True, exist_ok=True)
    fake_module_path = fake_scripts_dir / "local_loader_scheduler.py"
    shutil.copyfile(REPO_ROOT / "scripts" / "local_loader_scheduler.py", fake_module_path)

    spec = importlib.util.spec_from_file_location("local_loader_scheduler_under_test", fake_module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _mock_proc(returncode=0):
    """Build a mock subprocess.Popen() process: run_pipeline() switched from subprocess.run()
    to subprocess.Popen() (2026-08-11, tail-capture fix). Its reader thread does
    `for line in proc.stdout` then `proc.stdout.close()`, so the mock's .stdout must support
    both."""
    proc = MagicMock()
    proc.stdout = MagicMock()
    proc.stdout.__iter__.return_value = iter([])
    proc.poll.return_value = returncode
    proc.wait.return_value = returncode
    return proc


class TestIndependentLoaderContinuesAfterUpstreamFailure:
    def test_second_independent_loader_still_runs_after_first_fails(self, tmp_path):
        module = _load_scheduler_module(tmp_path)
        # "trend_analysis" and "sector_industry" have no LOADER_DEPENDENCIES entry between
        # them (neither declares a dependency on the other) - a real independent pair,
        # matching the real "scores" -> "buy_sell" case without depending on that exact
        # pipeline's current membership.
        procs = [_mock_proc(returncode=1), _mock_proc(returncode=0)]
        with (
            patch.object(module, "PIPELINES", {"test_pipeline": ["trend_analysis", "sector_industry"]}),
            patch.object(module, "reap_stale_running_loaders", return_value=[]),
            patch.object(module.subprocess, "Popen", side_effect=procs) as mock_popen,
            patch.object(module, "_mark_loader_failed_after_crash") as mock_mark,
        ):
            rc = module.run_pipeline("test_pipeline")

        # Both loaders were actually invoked - the second was not skipped.
        assert mock_popen.call_count == 2
        # Overall pipeline still reports failure (something did go wrong).
        assert rc == 1
        # Only the first (failed) loader got marked failed.
        mock_mark.assert_called_once()
        assert mock_mark.call_args.args[0] == "load_trend_analysis.py"

    def test_dependent_loader_is_still_skipped_after_its_real_dependency_fails(self, tmp_path):
        module = _load_scheduler_module(tmp_path)
        # Isolate from LOADER_DEPENDENCIES' real chains (value_quality_growth itself
        # requires financial_statements/valuations/analyst_earnings_estimates, which would
        # skip it before it even runs) - use a synthetic 2-loader dependency edge instead.
        with (
            patch.object(module, "PIPELINES", {"test_pipeline": ["trend_analysis", "sector_industry"]}),
            patch.object(module, "LOADER_DEPENDENCIES", {"sector_industry": ["trend_analysis"]}),
            patch.object(module, "reap_stale_running_loaders", return_value=[]),
            patch.object(module.subprocess, "Popen", return_value=_mock_proc(returncode=1)) as mock_popen,
            patch.object(module, "_mark_loader_failed_after_crash"),
        ):
            rc = module.run_pipeline("test_pipeline")

        # Only the first loader (trend_analysis) was actually invoked and failed -
        # sector_industry, which genuinely depends on it, was correctly skipped.
        assert mock_popen.call_count == 1
        assert rc == 1

    def test_all_success_still_returns_zero(self, tmp_path):
        module = _load_scheduler_module(tmp_path)
        with (
            patch.object(module, "PIPELINES", {"test_pipeline": ["trend_analysis", "sector_industry"]}),
            patch.object(module, "reap_stale_running_loaders", return_value=[]),
            patch.object(module.subprocess, "Popen", return_value=_mock_proc(returncode=0)) as mock_popen,
        ):
            rc = module.run_pipeline("test_pipeline")

        assert mock_popen.call_count == 2
        assert rc == 0
