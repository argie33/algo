#!/usr/bin/env python3
"""Daily entrypoint for XBRL data-quality layers 4, 5 and 6 (see MEMORY.md's
xbrl_calculation_linkbase_check_landed_20260910 and the "7 layers" docstring in
scripts/xbrl_calculation_linkbase_check.py for the full architecture).

Why this exists: layers 4 (scripts/xbrl_yfinance_crosscheck.py), 5
(scripts/xbrl_calculation_linkbase_check.py) and 6 (scripts/xbrl_dqc_arelle_check.py)
were all built "deliberately NOT part of every DataPatrol run" because each makes live
outbound requests (yfinance / SEC EDGAR) or shells out to a subprocess (arelleCmdLine)
through the same rate-limited/circuit-broken session every loader depends on - see
yfinance_validation_calls_self_triggered_ban_during_reload_20260903 in MEMORY.md. Their
own docstrings say "run by hand or from a low-frequency schedule (e.g. weekly)" - but
until this script, only the "by hand" half of that sentence was ever actually true.
Nothing invoked them automatically, so their value depended entirely on a human
remembering to run three extra commands on top of everything else.

Why DAILY, not weekly (corrected 2026-09-10 after a "verify the decision, not just the
code" pass): layers 4/5's own `_select_symbols()`/`_select_rotating_sample()` picks its
rotating sample via `ORDER BY md5(symbol || CURRENT_DATE::text)` - a sample explicitly
re-seeded by the calendar date, engineered for daily rotation through the universe
(CLAUDE.md's own description of this mechanism literally says "daily pseudo-random
sample"). Layer 6 (added here 2026-09-12, previously fully unscheduled) uses the exact
same `_select_rotating_sample()` pattern in scripts/xbrl_dqc_arelle_check.py - same
rationale applies. An earlier version of this script ran weekly, copying the
"e.g. weekly" example from the underlying scripts' docstrings (written for an
unscheduled, run-by-hand world) without checking that against the actual selection
mechanism. At the live-measured universe size (4,896 yfinance-crosscheck-eligible
symbols, 4,960 calc-linkbase-eligible symbols, 2026-09-10), weekly cadence would take
~3.8 years and ~6.4 years respectively to cycle through the full universe once - daily
drops that to ~6.5 and ~11 months. The documented self-triggered-ban risk is
specifically about a FULL-UNIVERSE run, not about the frequency of a small
(25/15/10-symbol) sample - daily at this sample size is still a small fraction of one
week's worth of what a single "check everything" run would cost.

Layer 7 (scripts/xbrl_segment_sum_reconciliation.py) is deliberately NOT included here:
its dataset (SEC's monthly "Financial Statement and Notes Data Sets" bulk download) only
publishes once a month, so a daily run would just re-check the same snapshot - it has its
own monthly schedule instead (see scripts/setup_windows_schedule.ps1's
xbrl-segment-sum-monthly task, or the AWS-side terraform equivalent).

Deliberately NOT folded into algo/algo_data_patrol.py / the DataPatrol task: that suite
runs twice a day (or after every local `--now metrics`/`--now all` reload, see
scripts/local_loader_scheduler.py's `_run_data_patrol_and_report`) as a hard-timeout gate
directly feeding Phase 1 (orchestrator halts if it's missing/stale/CRITICAL) - see
algo/orchestrator/phase1_data_freshness.py's _check_data_patrol_results. Adding
unpredictable-latency live network calls / subprocess invocations (SEC EDGAR, yfinance,
arelleCmdLine) into that same timeout budget risks turning an optional, informational
WARN-only cross-check into an accidental trading-halt trigger. This script runs on its
own independent daily schedule instead: locally via Windows Task Scheduler
(scripts/setup_windows_schedule.ps1's "xbrl-second-opinion" task, added 2026-09-12 -
this is the actual automation path for a local dev machine with no AWS account), and/or
in AWS via terraform/modules/loaders/main.tf's xbrl_second_opinion task+schedule (written
but not yet applied - needs real AWS access, unrelated to whether local automation works).
Same small-rotating-sample posture as running each script by hand, just no longer
dependent on anyone remembering to.

All three underlying scripts already write their own findings straight to
data_patrol_log (WARN severity, same data_patrol_review triage queue as every other
DataPatrol check) - this wrapper just calls their `run()` functions back to back with
the same defaults the docstrings recommend for a periodic pass, and lets any one
layer's failure (e.g. a transient SEC/yfinance outage, or Arelle/dqc_us_rules not being
installed - see xbrl_dqc_arelle_check.py's own module docstring for that optional
`pip install -r requirements-xbrl-dqc.txt` dependency) not block the others. Any
failure still exits nonzero after all layers have been attempted, so a partial failure
is not silently swallowed - see the exit-code comment at the bottom of main().

Runs cold every time in AWS, unlike an ad-hoc local run: all three scripts read a
companyfacts/calculation-linkbase disk cache (%TEMP%/algo-sec-edgar-cache, see
utils/external/sec_edgar_client.py) that's normally warm on a LOCAL dev box after a loader
run on the same machine - but each ECS Fargate task (this one included) gets its own fresh
ephemeral filesystem, so there is no cross-task cache to inherit there regardless of where
this runs. Not a correctness issue (all three fall back to live SEC/yfinance fetches
fine), just don't expect the "already warm" request-volume savings their docstrings
describe when this runs on its schedule - the fixed small sample size (25 + 15 + 10
symbols) is what actually keeps this within the shared rate-limit budget, not cache reuse.

Usage:
    python scripts/xbrl_second_opinion_daily.py
    python scripts/xbrl_second_opinion_daily.py --dry-run
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def _run_dqc_layer(*, limit: int, symbols_override: list[str] | None, dry_run: bool) -> dict[str, Any]:
    """Adapts xbrl_dqc_arelle_check's two-step (pick sample, then run) CLI shape to the
    same `fn(limit=..., symbols_override=..., dry_run=...)` call signature the other two
    layers already use, so main()'s loop below can call all three uniformly.
    """
    from scripts.xbrl_dqc_arelle_check import _select_rotating_sample
    from scripts.xbrl_dqc_arelle_check import run as run_dqc

    symbols = symbols_override if symbols_override is not None else _select_rotating_sample(limit)
    result = run_dqc(symbols=symbols, dry_run=dry_run)
    return {"sampled_symbols": result["checked"]}


def main(argv: list[str] | None = None) -> None:
    from scripts.xbrl_calculation_linkbase_check import run as run_calc_linkbase
    from scripts.xbrl_yfinance_crosscheck import run as run_yfinance_crosscheck

    # BUG FIX (2026-09-13): this wrapper had NO argument parsing at all - `--dry-run` was
    # silently ignored (sys.argv untouched) and every layer call below hardcoded
    # `dry_run=False`, so `python scripts/xbrl_second_opinion_daily.py --dry-run` actually
    # ran live and wrote real findings to data_patrol_log. Live-caught: a verification run
    # of this exact wrapper with --dry-run logged 5+1+1 real rows to the DB. The three
    # underlying scripts (xbrl_yfinance_crosscheck.py etc.) already have correct --dry-run
    # handling of their own - this wrapper just never threaded it through. `argv` defaults
    # to None (-> sys.argv[1:]) for real CLI use but lets tests pass an explicit list instead
    # of parsing the pytest process's own argv.
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run all three layers without writing findings to data_patrol_log.",
    )
    args = parser.parse_args(argv)

    started = time.monotonic()
    failures = 0

    layers = (
        ("yfinance_crosscheck", run_yfinance_crosscheck, 25),
        ("calculation_linkbase_check", run_calc_linkbase, 15),
        ("dqc_arelle_check", _run_dqc_layer, 10),
    )
    for label, fn, limit in layers:
        try:
            summary = fn(limit=limit, symbols_override=None, dry_run=args.dry_run)
            logger.info(f"[SECOND_OPINION_DAILY] {label}: sampled {summary['sampled_symbols']} symbol(s)")
        except Exception as e:
            # Non-fatal by design (see module docstring): a transient SEC/yfinance outage
            # or missing optional Arelle/dqc_us_rules install in one layer must not prevent
            # the others from running, and this task is deliberately independent of the
            # Phase-1-gating DataPatrol task - so a nonzero exit here is only for
            # operator visibility, never a halt.
            failures += 1
            logger.error(f"[SECOND_OPINION_DAILY] {label} failed: {e}", exc_info=True)

    elapsed = time.monotonic() - started
    logger.info(f"[SECOND_OPINION_DAILY] Done in {elapsed:.1f}s - {failures} of {len(layers)} layer(s) failed")
    # Always propagate ANY failure via exit code, even though every layer was still
    # attempted above - a partial failure must still mark this run failed so it's visible
    # (Task Scheduler's LastTaskResult locally, or the DLQ/CloudWatch alarm path via
    # aws_cloudwatch_event_target's dead_letter_config in terraform/modules/loaders/main.tf
    # if/when the AWS side is applied). Exiting 0 on a partial failure would silently drop
    # that visibility - the exact "depends on a human remembering to check" failure mode
    # this whole script exists to close.
    sys.exit(1 if failures > 0 else 0)


if __name__ == "__main__":
    main()
