#!/usr/bin/env python3
"""Standalone intraday portfolio-risk (beta/concentration) re-check, for a tight local cadence
between full orchestrator runs.

REAL-MONEY-READINESS FIX (2026-09-15, goal: "keeps failing halting", user confirmed local-only
deployment - no AWS). terraform/modules/services/intraday-risk-monitor.tf already builds this
exact check as an AWS Scheduler->Lambda invocation (`mode: "intraday_risk_monitor"` in
lambda/algo_orchestrator/lambda_function.py, every 15 minutes during market hours) so a position
that drifts past the portfolio beta cap or top-5-concentration cap purely from intraday price
movement - no new entry involved - is caught within minutes instead of only at the next full
orchestrator run (see algo/risk/intraday_risk_monitor.py's own module docstring for the full
gap this closes). That AWS path needs `terraform apply` against a real AWS account and is
`enable_intraday_risk_monitor = false` in terraform/prod.tfvars regardless - moot for a
local-only setup. `check_intraday_risk()` itself is pure Python (Alpaca live broker state + the
same HaltFlagManager already used locally in RDS mode) - this script is the local equivalent
entrypoint, registered as its own Windows Scheduled Task (see scripts/setup_windows_schedule.ps1)
instead of depending on a cloud deployment that was never applied.

Usage:
    python scripts/run_intraday_risk_monitor.py
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
    from algo.risk.intraday_risk_monitor import check_intraday_risk

    config = get_config()
    try:
        result = check_intraday_risk(config)
        logger.info(f"[INTRADAY_RISK_MONITOR] result={result}")
    except Exception as monitor_err:
        logger.critical(f"[INTRADAY_RISK_MONITOR CRITICAL] Check failed unexpectedly: {monitor_err}", exc_info=True)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
