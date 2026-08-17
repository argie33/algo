"""Regression test for the 2026-08-17 fix: a full (non---loaders) pipeline run hard-failed
any loader whose LOADER_DEPENDENCIES entry pointed at a loader that lives in a DIFFERENT
PIPELINES[] list entirely - e.g. "scores" (in PIPELINES["signals"]) depends on
"value_quality_growth"/"enhanced_quality_growth"/"positioning"/"stability_metrics" (all only
in PIPELINES["metrics"]). completed_loaders starts empty on every run_pipeline() call and only
ever gains entries from loaders THIS invocation executes, so a cross-pipeline dependency could
never appear in it - not for a standalone `--now signals`, and not even for `--now all` (each
pipeline gets its own run_pipeline() call with its own fresh completed_loaders).

Live-reproduced 2026-08-17: a `--now signals` run hard-failed scores/buy_sell/signal_quality/
algo on this exact gate minutes after a separate `metrics` run had freshly completed their
real dependencies - the root cause of stock_scores/signal_quality_scores sitting FAILED for
days (last successful stock_scores completion: 2026-08-13) while the actual upstream data was
hours-fresh in the DB the whole time. See scores_requires_cross_pipeline_deps_never_satisfied_20260817
memory for the live incident this reproduces.

Fix: dependencies outside the invoked pipeline's own declared loader roster (own_pipeline_loaders)
are always treated as assumed-fresh, the same trust model already used for deps deliberately
excluded via --loaders - just applied unconditionally, since these deps could never be satisfied
in-process regardless of --loaders. Same-pipeline dependencies keep full same-run enforcement.
"""

import importlib.util
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_scheduler_module(tmp_path):
    fake_scripts_dir = tmp_path / "scripts"
    fake_scripts_dir.mkdir(parents=True, exist_ok=True)
    fake_module_path = fake_scripts_dir / "local_loader_scheduler.py"
    shutil.copyfile(REPO_ROOT / "scripts" / "local_loader_scheduler.py", fake_module_path)

    spec = importlib.util.spec_from_file_location(
        "local_loader_scheduler_under_test_cross_pipeline_deps", fake_module_path
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _mock_proc(returncode=0):
    proc = MagicMock()
    proc.stdout = MagicMock()
    proc.stdout.__iter__.return_value = iter([])
    proc.poll.return_value = returncode
    proc.wait.return_value = returncode
    return proc


class TestCrossPipelineDependencyNotBlocking:
    def test_full_pipeline_run_does_not_block_on_a_different_pipelines_loader(self, tmp_path):
        """A standalone full run of PIPELINES["signals"]-equivalent must still run "scores"
        even though its dependency ("value_quality_growth") only exists in a different
        pipeline and can never be in completed_loaders for this invocation."""
        module = _load_scheduler_module(tmp_path)
        with (
            patch.object(
                module,
                "PIPELINES",
                {
                    "test_metrics": ["value_quality_growth"],
                    "test_signals": ["scores"],
                },
            ),
            patch.object(module, "LOADER_DEPENDENCIES", {"scores": ["value_quality_growth"]}),
            patch.object(module, "reap_stale_running_loaders", return_value=[]),
            patch.object(module.subprocess, "Popen", return_value=_mock_proc(returncode=0)) as mock_popen,
        ):
            rc = module.run_pipeline("test_signals")  # no --loaders - the real-world failure mode

        assert rc == 0
        assert mock_popen.call_count == 1
        invoked_cmd = mock_popen.call_args.args[0]
        assert any("load_scores" in str(part) or "stock_scores" in str(part) for part in invoked_cmd)

    def test_same_pipeline_dependency_still_hard_enforced(self, tmp_path):
        """Dependencies within the SAME pipeline's own roster must keep strict same-run
        enforcement - the fix only exempts genuinely cross-pipeline deps, not real ordering."""
        module = _load_scheduler_module(tmp_path)
        with (
            patch.object(
                module,
                "PIPELINES",
                {"test_metrics": ["value_quality_growth", "enhanced_quality_growth"]},
            ),
            patch.object(module, "LOADER_DEPENDENCIES", {"enhanced_quality_growth": ["value_quality_growth"]}),
            patch.object(module, "reap_stale_running_loaders", return_value=[]),
            patch.object(module.subprocess, "Popen", return_value=_mock_proc(returncode=1)) as mock_popen,
            patch.object(module, "_mark_loader_failed_after_crash"),
        ):
            rc = module.run_pipeline("test_metrics")

        # value_quality_growth ran (and failed) - enhanced_quality_growth, which genuinely
        # depends on it WITHIN THE SAME PIPELINE, must still be skipped, not silently trusted.
        assert mock_popen.call_count == 1
        assert rc == 1
