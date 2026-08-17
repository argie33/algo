"""Regression/feature test for the --loaders scoping flag (added 2026-08-17).

Context: scripts/local_loader_scheduler.py only ever supported `--now {pipeline}` -
all-or-nothing for every loader in a pipeline (metrics has 10, each backfill run
serialized behind one lock, taking 6-8h locally). There was no sanctioned way to
backfill just what's actually needed (e.g. positioning/stability_metrics) without either
waiting out a full multi-hour run or bypassing the scheduler to invoke a loader directly
(banned - see feedback_always_use_pipeline_scheduler_for_backfills - that skips status
tracking and dependency ordering and has caused its own incidents).

--loaders <comma-separated-shorthand-names> lets an operator scope a --now invocation to
a subset of a pipeline's loaders, still under the same lock and via the same sanctioned
entrypoint. Dependencies excluded from the subset are treated as already-satisfied by
existing DB state (that's the entire point - otherwise a scoped run would just
transitively pull in everything anyway). Uses real registered loader shorthand names
(normalize_loader_name() raises on anything unregistered, so synthetic names like "a"/"b"
used in other run_pipeline tests won't work once loader_filter validation runs) -
"positioning" genuinely depends on "company_info" in the real LOADER_DEPENDENCIES, which
is the exact motivating scenario for this flag.
"""

import importlib.util
import shutil
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_scheduler_module(tmp_path):
    """Load the real scheduler source from a copy under tmp_path - see
    test_local_loader_scheduler_independent_loader_continues_after_failure.py for why
    (avoids leaking real logs/load_*_<epoch>.log files into the repo's actual logs/ dir)."""
    fake_scripts_dir = tmp_path / "scripts"
    fake_scripts_dir.mkdir(parents=True, exist_ok=True)
    fake_module_path = fake_scripts_dir / "local_loader_scheduler.py"
    shutil.copyfile(REPO_ROOT / "scripts" / "local_loader_scheduler.py", fake_module_path)

    spec = importlib.util.spec_from_file_location("local_loader_scheduler_under_test_loaders_flag", fake_module_path)
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


class TestLoaderFilterScopesRunPipeline:
    def test_only_requested_loaders_are_invoked(self, tmp_path):
        module = _load_scheduler_module(tmp_path)
        with (
            patch.object(module, "PIPELINES", {"test_pipeline": ["trend_analysis", "sector_industry"]}),
            patch.object(module, "LOADER_DEPENDENCIES", {}),
            patch.object(module, "reap_stale_running_loaders", return_value=[]),
            patch.object(module.subprocess, "Popen", return_value=_mock_proc(returncode=0)) as mock_popen,
        ):
            rc = module.run_pipeline("test_pipeline", loader_filter={"sector_industry"})

        assert rc == 0
        assert mock_popen.call_count == 1
        invoked_cmd = mock_popen.call_args.args[0]
        assert any("load_sector_industry_daily.py" in str(part) for part in invoked_cmd)

    def test_dependency_excluded_from_filter_is_assumed_fresh_not_blocking(self, tmp_path):
        """The whole point of --loaders: requesting just 'positioning' when it depends on
        'company_info' must not skip it just because company_info wasn't included in this
        run - company_info is assumed already-fresh from a prior/concurrent run, exactly
        the real scenario that motivated this flag (see
        scores_factor_inputs_population_audit_20260817 memory)."""
        module = _load_scheduler_module(tmp_path)
        with (
            patch.object(module, "PIPELINES", {"test_pipeline": ["company_info", "positioning"]}),
            patch.object(module, "LOADER_DEPENDENCIES", {"positioning": ["company_info"]}),
            patch.object(module, "reap_stale_running_loaders", return_value=[]),
            patch.object(module.subprocess, "Popen", return_value=_mock_proc(returncode=0)) as mock_popen,
        ):
            rc = module.run_pipeline("test_pipeline", loader_filter={"positioning"})

        assert rc == 0
        assert mock_popen.call_count == 1
        invoked_cmd = mock_popen.call_args.args[0]
        assert any("load_positioning_metrics.py" in str(part) for part in invoked_cmd)

    def test_dependency_within_the_filtered_scope_is_still_enforced(self, tmp_path):
        """If both the dependency and its dependent are IN the requested subset, existing
        same-run ordering safety must still apply (this flag scopes what runs, it doesn't
        weaken intra-run dependency enforcement)."""
        module = _load_scheduler_module(tmp_path)
        with (
            patch.object(module, "PIPELINES", {"test_pipeline": ["company_info", "positioning"]}),
            patch.object(module, "LOADER_DEPENDENCIES", {"positioning": ["company_info"]}),
            patch.object(module, "reap_stale_running_loaders", return_value=[]),
            patch.object(module.subprocess, "Popen", return_value=_mock_proc(returncode=1)) as mock_popen,
            patch.object(module, "_mark_loader_failed_after_crash"),
        ):
            rc = module.run_pipeline("test_pipeline", loader_filter={"company_info", "positioning"})

        # Only company_info actually ran (and failed) - positioning, which genuinely
        # depends on it, was correctly skipped, same as the existing (non-subset)
        # dependency-enforcement behavior.
        assert mock_popen.call_count == 1
        assert rc == 1

    def test_unknown_loader_name_in_filter_errors_without_running_anything(self, tmp_path):
        module = _load_scheduler_module(tmp_path)
        with (
            patch.object(module, "PIPELINES", {"test_pipeline": ["trend_analysis", "sector_industry"]}),
            patch.object(module.subprocess, "Popen") as mock_popen,
        ):
            rc = module.run_pipeline("test_pipeline", loader_filter={"nonexistent"})

        assert rc == 1
        mock_popen.assert_not_called()


class TestLoadersFlagCliWiring:
    def test_loaders_flag_rejected_with_now_all(self, tmp_path, monkeypatch):
        module = _load_scheduler_module(tmp_path)
        module.__file__ = str(tmp_path / "scripts" / "local_loader_scheduler.py")
        monkeypatch.setattr(sys, "argv", ["local_loader_scheduler.py", "--now", "all", "--loaders", "positioning"])
        real_stdout, real_stderr = sys.stdout, sys.stderr
        try:
            with pytest.raises(SystemExit):
                module.main()
        finally:
            sys.stdout, sys.stderr = real_stdout, real_stderr

    def test_loaders_flag_parsed_and_passed_through_to_run_pipeline(self, tmp_path, monkeypatch):
        module = _load_scheduler_module(tmp_path)
        module.__file__ = str(tmp_path / "scripts" / "local_loader_scheduler.py")
        monkeypatch.setattr(
            sys,
            "argv",
            ["local_loader_scheduler.py", "--now", "metrics", "--loaders", "positioning,stability_metrics"],
        )
        real_stdout, real_stderr = sys.stdout, sys.stderr
        try:
            with (
                patch.object(module.tempfile, "gettempdir", return_value=str(tmp_path)),
                patch.object(module, "run_pipeline", return_value=0) as mock_run_pipeline,
            ):
                rc = module.main()
        finally:
            sys.stdout, sys.stderr = real_stdout, real_stderr

        assert rc == 0
        mock_run_pipeline.assert_called_once_with("metrics", loader_filter={"positioning", "stability_metrics"})
