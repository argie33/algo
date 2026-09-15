#!/usr/bin/env python3
"""Standalone stop-loss-guardian check, for a tight local intraday cadence between full
orchestrator runs.

REAL-MONEY-READINESS FIX (2026-09-15, goal: "keeps failing halting", user confirmed local-only
deployment - no AWS). terraform/modules/services/stop-loss-guardian.tf already builds this exact
check as an AWS Scheduler->Lambda invocation (`mode: "stop_loss_guardian"` in
lambda/algo_orchestrator/lambda_function.py), timed every 15 minutes during market hours so a
missing/expired stop-loss leg is caught and self-repaired within minutes instead of waiting for
the next scheduled orchestrator run (up to ~3.5h apart, per AlgoTrading_Orchestrator_* spacing).
That AWS path needs `terraform apply` against a real AWS account - moot for a local-only setup,
and unverifiable from a dev sandbox regardless (see stop_loss_guardian_terraform_apply_unverified
memory note). The check itself (`_verify_open_position_stop_loss_protection_step`,
phase9_reconciliation.py) is pure Python with no AWS dependency beyond the DB/Alpaca clients this
app already uses locally - this script is the local equivalent entrypoint, registered as its own
Windows Scheduled Task (see scripts/setup_windows_schedule.ps1) instead of only running as part
of each full orchestrator cycle.

`sync_positions_first=True` mirrors exactly how the AWS guardian dispatch calls this function -
without a preceding full reconciliation step (unlike the main orchestrator flow), so this
performs its own narrow position-only sync first to avoid false "missing stop leg" alarms on a
position that already closed since the last full run.

Usage:
    python scripts/run_stop_loss_guardian.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from utils.dotenv_loader import load_env_local

load_env_local()

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    from scripts.load_credentials import ensure_credentials_loaded

    ensure_credentials_loaded()
except Exception as e:
    logging.getLogger(__name__).warning(f"[CREDS] Could not load credentials from database: {e}")

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def main() -> int:
    from algo.infrastructure.config import get_config
    from algo.orchestrator.phase9_reconciliation import _verify_open_position_stop_loss_protection_step

    def _log_guardian_result(*args: object, **kwargs: object) -> None:
        logger.info(f"[STOP_LOSS_GUARDIAN] phase_result: args={args} kwargs={kwargs}")

    config = get_config()
    try:
        _verify_open_position_stop_loss_protection_step(_log_guardian_result, config, sync_positions_first=True)
    except Exception as guardian_err:
        logger.critical(
            f"[STOP_LOSS_GUARDIAN CRITICAL] Guardian run failed unexpectedly: {guardian_err}", exc_info=True
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
