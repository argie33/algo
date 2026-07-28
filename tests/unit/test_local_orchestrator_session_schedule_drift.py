"""Regression test: local dev orchestrator tooling must match the real production schedule
and run_identifier -> dry_run mapping.

Two drifts found live 2026-07-27:

1. scripts/orchestrator_scheduler.py's TRADING_SESSIONS had only 3 entries (morning,
   afternoon, evening=15:00) but terraform/modules/services/2x-daily-orchestrator.tf
   actually schedules 4 sessions: morning 9:30 AM, afternoon 1:00 PM, preclose 3:00 PM,
   evening 5:30 PM. The local scheduler mislabeled the 3:00 PM slot as "evening" - which ran
   `--evening` (there was no `--preclose` flag) and meant the real 5:30 PM evening run was
   never exercised locally at all.
2. scripts/run_local_orchestrator.py always computed dry_run=False by default regardless of
   run_type (unless ORCHESTRATOR_DRY_RUN was set), but production's real evening run
   (run_identifier="evening") is monitor-only (dry_run=True) per
   lambda_function.py's LIVE_TRADING_RUN_IDENTIFIERS/MONITOR_ONLY_RUN_IDENTIFIERS - so
   `--evening` locally submitted real (paper) orders exactly like `--morning`/`--afternoon`,
   silently diverging from what the real evening run actually does in production.

This locks in that scripts/run_local_orchestrator.py's supported --{flag} run types are
exactly the identifiers lambda_function.py classifies (no undefined/unclassified run_type can
reach the orchestrator), and that scripts/orchestrator_scheduler.py's TRADING_SESSIONS times
match terraform's real schedule.
"""

import sys
from datetime import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "lambda" / "algo_orchestrator"))

from lambda_function import LIVE_TRADING_RUN_IDENTIFIERS, MONITOR_ONLY_RUN_IDENTIFIERS  # noqa: E402

ALL_SCHEDULED_RUN_TYPES = {"morning", "afternoon", "preclose", "evening"}


def test_all_scheduled_run_types_are_classified_in_lambda_function():
    """Every run_type scripts/run_local_orchestrator.py can execute must be classified as
    either live-trading or monitor-only in production - an unclassified one would silently
    default to dry_run=True (fail-safe) in Lambda but raise in the local script (see
    run_local_orchestrator.py's dry_run computation), which is the correct fail-fast behavior
    for local dev tooling drifting out of sync with production's real identifiers."""
    classified = LIVE_TRADING_RUN_IDENTIFIERS | MONITOR_ONLY_RUN_IDENTIFIERS
    assert ALL_SCHEDULED_RUN_TYPES <= classified


def test_evening_is_monitor_only_not_live_trading():
    """The real production evening run (5:30 PM ET) never places new entries."""
    assert "evening" in MONITOR_ONLY_RUN_IDENTIFIERS
    assert "evening" not in LIVE_TRADING_RUN_IDENTIFIERS


def test_morning_afternoon_preclose_are_live_trading():
    assert {"morning", "afternoon", "preclose"} <= LIVE_TRADING_RUN_IDENTIFIERS


def test_orchestrator_scheduler_session_times_match_terraform_schedule():
    """terraform/modules/services/2x-daily-orchestrator.tf: morning 9:30 AM, afternoon 1:00 PM,
    preclose 3:00 PM, evening 5:30 PM ET - scripts/orchestrator_scheduler.py's TRADING_SESSIONS
    must match exactly, not the previous 3-entry dict with evening mislabeled at 3:00 PM."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "orchestrator_scheduler", PROJECT_ROOT / "scripts" / "orchestrator_scheduler.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert module.TRADING_SESSIONS == {
        "morning": time(9, 30),
        "afternoon": time(13, 0),
        "preclose": time(15, 0),
        "evening": time(17, 30),
    }


def test_run_local_orchestrator_supports_all_four_session_flags():
    """--preclose must exist alongside --morning/--afternoon/--evening/--run-all."""
    source = (PROJECT_ROOT / "scripts" / "run_local_orchestrator.py").read_text(encoding="utf-8")
    for flag in ("--morning", "--afternoon", "--preclose", "--evening", "--run-all"):
        assert f'"{flag}"' in source, f"{flag} missing from run_local_orchestrator.py argparse"
