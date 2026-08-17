"""Scheduled-task entry point: runs morning -> metrics -> signals in sequence.

ADDED 2026-08-17: this local dev environment had zero automated retry for the data-loading
pipelines - only 3x/day read-only orchestrator Scheduled Tasks existed (verified via
`Get-ScheduledTask`), and actual loading was manual-invocation-only. That's the structural
reason stock_scores/stability_metrics sat CRIT STALE for days: a hung/crashed run just sat
there until a human (or an ad-hoc Claude Code session) happened to notice and re-run it by
hand, and multiple sessions doing that independently is what caused this repo's repeated
concurrent-session collisions (see memory/concurrent_session_git_races_20260811.md).

Each stage below is a plain `--now <pipeline>` invocation - local_loader_scheduler.py's own
single-instance file lock (scripts/local_loader_scheduler.py's algo-scheduler.lock) already
makes a colliding invocation harmless: it logs a rejection and exits in seconds rather than
double-running or corrupting state (verified live tonight). So this wrapper does not need its
own coordination logic - it just attempts all three stages, in order, and lets the existing
lock and per-loader watermark-skip logic handle overlaps and idempotency.
"""

import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
STAGES = ["morning", "metrics", "signals"]
PER_STAGE_TIMEOUT_SEC = 6 * 3600  # generous ceiling; local_loader_scheduler.py enforces its
# own per-loader timeouts internally, this is just a backstop against the whole invocation
# wedging on something outside any individual loader's own timeout (e.g. a hung DB connect).


def main() -> int:
    overall_rc = 0
    for stage in STAGES:
        print(f"[PIPELINE_RUNNER] Starting stage: {stage}", flush=True)
        start = time.time()
        try:
            result = subprocess.run(
                [sys.executable, str(REPO_ROOT / "scripts" / "local_loader_scheduler.py"), "--now", stage],
                cwd=str(REPO_ROOT),
                timeout=PER_STAGE_TIMEOUT_SEC,
            )
            rc = result.returncode
        except subprocess.TimeoutExpired:
            print(
                f"[PIPELINE_RUNNER] Stage {stage} exceeded {PER_STAGE_TIMEOUT_SEC}s wrapper "
                f"timeout - moving on to the next stage rather than blocking the whole chain.",
                flush=True,
            )
            rc = 1
        elapsed = time.time() - start
        print(f"[PIPELINE_RUNNER] Stage {stage} finished: rc={rc} elapsed={elapsed:.0f}s", flush=True)
        if rc != 0:
            overall_rc = rc
        # Deliberately continue to the next stage even on failure/lock-rejection: a rejected
        # `metrics` attempt (another session already running it) doesn't mean `signals` should
        # be skipped too - signals' own LOADER_DEPENDENCIES check will correctly gate on
        # whatever metrics outputs actually exist by the time signals runs.

    print(f"[PIPELINE_RUNNER] All stages attempted. Final rc={overall_rc}", flush=True)
    return overall_rc


if __name__ == "__main__":
    sys.exit(main())
