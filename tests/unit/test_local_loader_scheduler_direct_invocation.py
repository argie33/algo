"""Regression test: every loader must be invoked as `python loaders/{file}.py` directly by
run_pipeline(), never routed through scripts/run_loader.py's generic class-lookup path.

Supersedes test_local_loader_scheduler_function_based_loaders_direct_invocation.py and
test_local_loader_scheduler_trend_analysis_direct_invocation.py, both deleted. Those tests
asserted the old per-loader special-case ladder in local_loader_scheduler.py (`elif loader ==
"trend_analysis": ...`) by parsing the source with `ast`. That ladder was independently patched
5 separate times ("Nth main()-bypass instance" commits: financial_statements, buy_sell, prices,
trend_analysis, economic) after each loader's main()-only logic was found silently skipped by
scripts/run_loader.py's generic OptimalLoader-class introspection path - and a follow-up audit
still found 2 more loaders (load_technical_indicators.py's schema migrations + hang-detection
heartbeat, load_positioning_metrics.py's crash-safe data_unavailable marking) exposed to the
exact same bug because nobody had special-cased them into the ladder yet.

Root-cause fix (2026-08-10): removed the ladder entirely - run_pipeline() now always invokes
`loaders/{file}.py` directly (production's real entrypoint, matching
terraform/modules/loaders/main.tf) for every loader, so there is no generic-path branch left to
silently diverge from production and no ladder left to grow an 8th special case. This test
asserts that invariant directly, across every registered loader, instead of parsing source for
`elif` branches - so it can't regress back to a partial special-case list without failing CI.
"""

import importlib.util
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from loaders.loader_registry import SHORTHAND_TO_FILENAME, normalize_loader_name

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_scheduler_module():
    spec = importlib.util.spec_from_file_location(
        "local_loader_scheduler_under_test", REPO_ROOT / "scripts" / "local_loader_scheduler.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _mock_proc(returncode=0):
    """Build a mock subprocess.Popen() process: run_pipeline() switched from subprocess.run()
    to subprocess.Popen() (2026-08-11, tail-capture fix) so a crash's real output can be
    attached to the failure message. Its reader thread does `for line in proc.stdout` then
    `proc.stdout.close()`, so the mock's .stdout must support both.

    SESSION 106 switched the main loop from a blocking proc.wait() to a non-blocking
    proc.poll() poll loop. .poll() must be configured too - an unconfigured MagicMock's
    .poll() returns a truthy mock object (never None), which the real loop reads as "process
    already finished" with that mock object AS the returncode, immediately treating every
    loader as crashed and writing a real "subprocess exited with code <MagicMock ...>" FAILED
    row via the real (unmocked) LoaderStatusManager. Live-confirmed 2026-08-16: this exact bug
    corrupted data_loader_status for price_daily/earnings_calendar in the real dev DB."""
    proc = MagicMock()
    proc.stdout = MagicMock()
    proc.stdout.__iter__.return_value = iter([])
    proc.poll.return_value = returncode
    proc.wait.return_value = returncode
    return proc


@pytest.mark.parametrize("shorthand", sorted(SHORTHAND_TO_FILENAME.keys()))
def test_every_loader_is_invoked_via_direct_module_execution(shorthand):
    module = _load_scheduler_module()
    filename = normalize_loader_name(shorthand)
    with (
        patch.object(module, "PIPELINES", {"test_pipeline": [shorthand]}),
        patch.object(module, "_check_loader_dependencies", return_value=True),
        patch.object(module, "reap_stale_running_loaders", return_value=[]),
        patch.object(module.subprocess, "Popen", return_value=_mock_proc()) as mock_popen,
    ):
        rc = module.run_pipeline("test_pipeline")

    assert rc == 0
    cmd = mock_popen.call_args.args[0]
    assert cmd == [module.sys.executable, f"loaders/{filename}"], (
        f"{shorthand} ({filename}) must be invoked as `python loaders/{filename}` directly, "
        f"not routed through scripts/run_loader.py's generic path. Got: {cmd}"
    )


def test_financial_statements_still_gets_statement_type_all_env_var():
    """The one loader that still needs a special case: not a different cmd, just an env var -
    financial_statements' main() fans LOADER_STATEMENT_TYPE="all" out to all 6 statement/period
    combos; the class constructor alone requires one specific combo to already be named."""
    module = _load_scheduler_module()
    with (
        patch.object(module, "PIPELINES", {"test_pipeline": ["financial_statements"]}),
        patch.object(module, "_check_loader_dependencies", return_value=True),
        patch.object(module, "reap_stale_running_loaders", return_value=[]),
        patch.object(module.subprocess, "Popen", return_value=_mock_proc()) as mock_popen,
    ):
        module.run_pipeline("test_pipeline")

    assert mock_popen.call_args.kwargs["env"]["LOADER_STATEMENT_TYPE"] == "all"


def test_run_loader_py_generic_path_never_invoked():
    """scripts/run_loader.py must never appear in a run_pipeline() subprocess command - its
    generic class-lookup path is the whole bug class this fix eliminates."""
    module = _load_scheduler_module()
    all_shorthands = list(SHORTHAND_TO_FILENAME.keys())
    with (
        patch.object(module, "PIPELINES", {"test_pipeline": all_shorthands}),
        patch.object(module, "_check_loader_dependencies", return_value=True),
        patch.object(module, "reap_stale_running_loaders", return_value=[]),
        patch.object(module.subprocess, "Popen", side_effect=lambda *a, **k: _mock_proc()) as mock_popen,
    ):
        rc = module.run_pipeline("test_pipeline")

    assert rc == 0
    for call in mock_popen.call_args_list:
        cmd = call.args[0]
        assert "scripts/run_loader.py" not in cmd, f"Found generic-path invocation: {cmd}"
