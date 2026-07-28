"""Regression test: an ambient ORCHESTRATOR_DRY_RUN env var must not silently defeat
--evening's documented "always monitor-only, never places new entries" guarantee.

Found live 2026-07-28: scripts/run_local_orchestrator.py's dry_run_override logic lets
any set ORCHESTRATOR_DRY_RUN value (even "false") take precedence over the run_type ->
dry_run mapping with zero indication to the operator. A shell that happens to carry
ORCHESTRATOR_DRY_RUN=false (e.g. left over from earlier debugging, not from .env.local)
causes `--evening` to silently stop being monitor-only, contradicting both the module's
own docstring and its --help text ("evening ... does not place new entries"). This is a
static source check (matching test_exit_notification_failure_does_not_rollback_exit.py's
rationale) rather than a full mocked invocation, since main() has a large dependency graph
(DB, orchestrator, credentials) not worth mocking just to exercise one branch.
"""

from pathlib import Path

SOURCE = (Path(__file__).parent.parent.parent / "scripts" / "run_local_orchestrator.py").read_text()


def _dry_run_override_block() -> str:
    start = SOURCE.index("dry_run_override = os.environ.get")
    end = SOURCE.index("elif run_type in MONITOR_ONLY_RUN_IDENTIFIERS", start)
    return SOURCE[start:end]


def test_env_override_defeating_monitor_only_default_prints_a_warning():
    block = _dry_run_override_block()
    assert "MONITOR_ONLY_RUN_IDENTIFIERS" in block, (
        "the dry_run_override branch must check whether run_type is monitor-only before "
        "silently accepting an env override that disagrees with that guarantee"
    )
    assert "WARNING" in block, (
        "an ORCHESTRATOR_DRY_RUN override that defeats a monitor-only run_type's "
        "dry_run=True default must print a visible warning - silently proceeding lets "
        "--evening's documented safety guarantee break with zero operator indication"
    )
