#!/usr/bin/env python3
"""Daily ECS entrypoint for XBRL data-quality layers 4 and 5 (see MEMORY.md's
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

Why DAILY, not weekly (corrected 2026-09-10 after a "verify the decision, not just the
code" pass): both scripts' own `_select_symbols()` picks its rotating sample via
`ORDER BY md5(symbol || CURRENT_DATE::text)` - a sample explicitly re-seeded by the
calendar date, engineered for daily rotation through the universe (CLAUDE.md's own
description of this mechanism literally says "daily pseudo-random sample"). An earlier
version of this script ran weekly, copying the "e.g. weekly" example from the two
underlying scripts' docstrings (written for an unscheduled, run-by-hand world) without
checking that against the actual selection mechanism. At the live-measured universe
size (4,896 yfinance-crosscheck-eligible symbols, 4,960 calc-linkbase-eligible symbols,
2026-09-10), weekly cadence would take ~3.8 years and ~6.4 years respectively to cycle
through the full universe once - daily drops that to ~6.5 and ~11 months. The documented
self-triggered-ban risk is specifically about a FULL-UNIVERSE run, not about the
frequency of a small (25/15-symbol) sample - daily at this sample size is still a small
fraction of one week's worth of what a single "check everything" run would cost, it just
multiplies the weekly total by 7x (25->175, 15->105) - trivial next to "full universe."

Deliberately NOT folded into algo/algo_data_patrol.py / the DataPatrol ECS task: that
task runs twice a day as a hard-timeout (600s) Step Functions state directly gating
Phase 1 (orchestrator halts if it's missing/stale/CRITICAL) - see
algo/orchestrator/phase1_data_freshness.py's _check_data_patrol_results. Adding
unpredictable-latency live network calls (SEC EDGAR + yfinance, dozens of requests)
into that same timeout budget risks turning an optional, informational WARN-only
cross-check into an accidental trading-halt trigger. This script is wired to its own
independent daily EventBridge trigger instead (terraform/modules/loaders/main.tf,
xbrl_second_opinion task + schedule) - same small-rotating-sample posture as running
each script by hand, just no longer dependent on anyone remembering to.

Both underlying scripts already write their own findings straight to data_patrol_log
(WARN severity, same data_patrol_review triage queue as every other DataPatrol check) -
this wrapper just calls their `run()` functions back to back with the same defaults
the docstrings recommend for a periodic pass, and lets either one's failure (e.g. a
transient SEC/yfinance outage) not block the other. Any failure still exits nonzero
after both layers have been attempted, so a 1-of-2 failure is not silently swallowed -
see the exit-code comment at the bottom of main().

Runs cold every time in AWS, unlike an ad-hoc local run: both scripts read a companyfacts/
calculation-linkbase disk cache (%TEMP%/algo-sec-edgar-cache, see
utils/external/sec_edgar_client.py) that's normally warm on a LOCAL dev box after a loader
run on the same machine - but each ECS Fargate task (this one included) gets its own fresh
ephemeral filesystem, so there is no cross-task cache to inherit here regardless of where
this runs. Not a correctness issue (both scripts fall back to live SEC/yfinance fetches
fine), just don't expect the "already warm" request-volume savings their docstrings
describe when this runs on its schedule - the fixed small sample size (25 + 15 symbols)
is what actually keeps this within the shared rate-limit budget, not cache reuse.

Usage:
    python scripts/xbrl_second_opinion_daily.py
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
            logger.info(f"[SECOND_OPINION_DAILY] {label}: sampled {summary['sampled_symbols']} symbol(s)")
        except Exception as e:
            # Non-fatal by design (see module docstring): a transient SEC/yfinance outage
            # in one layer must not prevent the other from running, and this task is
            # deliberately independent of the Phase-1-gating DataPatrol task - so a
            # nonzero exit here is only for operator/CloudWatch visibility, never a halt.
            failures += 1
            logger.error(f"[SECOND_OPINION_DAILY] {label} failed: {e}", exc_info=True)

    elapsed = time.monotonic() - started
    logger.info(f"[SECOND_OPINION_DAILY] Done in {elapsed:.1f}s - {failures} of 2 layer(s) failed")
    # Always propagate ANY failure via exit code, even though both layers were still
    # attempted above - a 1-of-2 failure must still mark the ECS task failed so it reaches
    # the DLQ/CloudWatch alarm path (aws_cloudwatch_event_target's dead_letter_config in
    # terraform/modules/loaders/main.tf). Exiting 0 on a partial failure would silently
    # drop that visibility - the exact "depends on a human remembering to check" failure
    # mode this whole script exists to close.
    sys.exit(1 if failures > 0 else 0)


if __name__ == "__main__":
    main()
