#!/usr/bin/env python3
"""Weekly ECS entrypoint for XBRL data-quality layers 4 and 5 (see MEMORY.md's
xbrl_calculation_linkbase_check_landed_20260910 and the "5 layers" docstring in
scripts/xbrl_calculation_linkbase_check.py for the full architecture).

Why this exists: layers 4 (scripts/xbrl_yfinance_crosscheck.py) and 5
(scripts/xbrl_calculation_linkbase_check.py) were both built "deliberately NOT part of
every DataPatrol run" because each makes live outbound requests (yfinance / SEC EDGAR)
through the same rate-limited/circuit-broken session every loader depends on - see
yfinance_validation_calls_self_triggered_ban_during_reload_20260903 in MEMORY.md. Their
own docstrings say "run by hand or from a low-frequency schedule (e.g. weekly)" - but
until this script, only the "by hand" half of that sentence was ever actually true.
Nothing invoked them automatically, so their value depended entirely on a human
remembering to run two extra commands on top of everything else.

Deliberately NOT folded into algo/algo_data_patrol.py / the DataPatrol ECS task: that
task runs twice a day as a hard-timeout (600s) Step Functions state directly gating
Phase 1 (orchestrator halts if it's missing/stale/CRITICAL) - see
algo/orchestrator/phase1_data_freshness.py's _check_data_patrol_results. Adding
unpredictable-latency live network calls (SEC EDGAR + yfinance, dozens of requests)
into that same timeout budget risks turning an optional, informational WARN-only
cross-check into an accidental trading-halt trigger. This script is wired to its own
independent weekly EventBridge trigger instead (terraform/modules/loaders/main.tf,
xbrl_second_opinion task + schedule) - same small-rotating-sample posture as running
each script by hand, just no longer dependent on anyone remembering to.

Both underlying scripts already write their own findings straight to data_patrol_log
(WARN severity, same data_patrol_review triage queue as every other DataPatrol check) -
this wrapper just calls their `run()` functions back to back with the same defaults
the docstrings recommend for a periodic pass, and lets either one's failure (e.g. a
transient SEC/yfinance outage) not block the other.

Usage:
    python scripts/xbrl_second_opinion_weekly.py
"""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def main() -> None:
    from scripts.xbrl_calculation_linkbase_check import run as run_calc_linkbase
    from scripts.xbrl_yfinance_crosscheck import run as run_yfinance_crosscheck

    started = time.monotonic()
    failures = 0

    for label, fn, limit in (
        ("yfinance_crosscheck", run_yfinance_crosscheck, 25),
        ("calculation_linkbase_check", run_calc_linkbase, 15),
    ):
        try:
            summary = fn(limit=limit, symbols_override=None, dry_run=False)
            logger.info(f"[SECOND_OPINION_WEEKLY] {label}: sampled {summary['sampled_symbols']} symbol(s)")
        except Exception as e:
            # Non-fatal by design (see module docstring): a transient SEC/yfinance outage
            # in one layer must not prevent the other from running, and this task is
            # deliberately independent of the Phase-1-gating DataPatrol task - so a
            # nonzero exit here is only for operator/CloudWatch visibility, never a halt.
            failures += 1
            logger.error(f"[SECOND_OPINION_WEEKLY] {label} failed: {e}", exc_info=True)

    elapsed = time.monotonic() - started
    logger.info(f"[SECOND_OPINION_WEEKLY] Done in {elapsed:.1f}s - {failures} of 2 layer(s) failed")
    sys.exit(1 if failures == 2 else 0)


if __name__ == "__main__":
    main()
