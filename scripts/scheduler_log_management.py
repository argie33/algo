"""Log rotation/retention helpers for scripts/local_loader_scheduler.py.

Extracted 2026-09-15 to keep local_loader_scheduler.py under the file-size ratchet's 2000-line
hard ceiling (see .file-size-baseline.json / .pre-commit-scripts/check_file_size_ratchet.py) -
pure housekeeping logic with no dependency on the rest of that file, split out rather than
trimmed for content.
"""

# BUG FOUND 2026-09-14 (real-money-readiness audit, goal: "algo keeps halting and failing"):
# logs/scheduler_invocations.log is opened "a" (append) forever with no size cap or rotation -
# every invocation since this tee was added 2026-08-16 has accumulated into one file that had
# grown to 11GB/tens of millions of lines by tonight (mostly the per-row "Unmapped SEC field"
# spam fixed elsewhere in this session, see loaders/helpers/sec_base.py) - and would keep
# growing unbounded even after that fix, since nothing here ever caps or rotates it. That's
# exactly the failure mode that incident already demonstrated: an oversized log file degraded
# this process's own I/O throughput enough to trip phase1_failsafe_retry.py's stall/timeout
# detection and false-FAIL otherwise-successful loader runs.
#
# FOLLOW-UP FIX (2026-09-15, same day): the size-based rename-to-.1-backup approach committed
# earlier today does NOT work on this dev machine - live-reproduced: this pipeline is nearly
# always running at least one scheduler invocation, and Windows refuses `os.rename()`/
# `Path.rename()` on a file another process still has open for writing (PermissionError
# [WinError 32]), unlike POSIX where rename-while-open is fine. The rotation function's own
# `except OSError` fail-open path was silently swallowing this EVERY time, so the 10.98GB file
# never actually got rotated by the "fix" that landed a few hours ago - confirmed live by
# attempting the exact same rename this function performs while pid holding the file open was
# still running, and reproducing the identical PermissionError.
#
# Real fix: stop sharing ONE ever-growing file across every invocation, which is what made
# rotation need to touch a file concurrent processes have open in the first place. Write to a
# DATE-STAMPED file instead (a new file each day, never renamed/touched while old ones are
# still open) and separately delete old dated files past a retention window at startup -
# deleting a file nobody has open anymore always works on Windows, unlike renaming one that
# might still be open. The old undated logs/scheduler_invocations.log is left alone (still
# open by whatever process was already writing it) - it simply stops receiving new writes and
# can be deleted by hand once nothing holds it (check via `tasklist`/lock liveness first, same
# as any other "is this process really done" check in this codebase).
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

_SCHEDULER_LOG_RETENTION_DAYS = 14
_SCHEDULER_LOG_MAX_BYTES = 200 * 1024 * 1024  # 200MB, same-day safety net (best-effort only)


def _dated_scheduler_log_path(logs_dir: Path) -> Path:
    return logs_dir / f"scheduler_invocations_{datetime.now(timezone.utc):%Y%m%d}.log"


def _cleanup_old_scheduler_logs(logs_dir: Path, retention_days: int = _SCHEDULER_LOG_RETENTION_DAYS) -> None:
    cutoff = time.time() - retention_days * 86400
    for old_log in logs_dir.glob("scheduler_invocations_*.log"):
        try:
            if old_log.stat().st_mtime < cutoff:
                old_log.unlink()
        except OSError as e:
            # Best-effort, same fail-open discipline as rotation below - a stale file that's
            # somehow still locked (or a permissions hiccup) must never block a real run.
            print(f"[LOCAL_SCHEDULER] WARNING: Could not delete old log {old_log.name}: {e}", file=sys.stderr)


# FOUND 2026-09-15 (same audit pass as the scheduler_invocations.log fix above): the per-loader
# tee logs this scheduler writes (see `full_log_path` in run_pipeline, local_loader_scheduler.py
# - one new `{loader}_{unix_ts}.log` file per invocation, added 2026-08-16 for stall
# diagnosability) have the exact same "never cleaned up, ever" gap the scheduler log had before
# today's fix - just spread across many files instead of one. Live-confirmed: logs/ is 21GB,
# with individual load_financial_statements_*.log files up to 1.7GB each, accumulating since
# 2026-09-07 with nothing anywhere in the codebase ever deleting one. Same risk as the bug just
# fixed above (oversized log I/O degrading throughput enough to trip phase1_failsafe_retry.py
# stall detection) plus plain disk exhaustion. Each run already gets its own never-reopened file
# (no Windows open-file-rename problem here, unlike the shared scheduler log), so a straight
# retention-window delete at startup is sufficient - no rotation needed.
def _cleanup_old_loader_run_logs(logs_dir: Path, retention_days: int = _SCHEDULER_LOG_RETENTION_DAYS) -> None:
    cutoff = time.time() - retention_days * 86400
    for old_log in logs_dir.glob("*.log"):
        if old_log.name.startswith("scheduler_invocations"):
            continue  # handled separately by _cleanup_old_scheduler_logs above
        try:
            if old_log.stat().st_mtime < cutoff:
                old_log.unlink()
        except OSError as e:
            # Best-effort, same fail-open discipline as everything else in this file - a stale
            # file that's somehow still locked (or a permissions hiccup) must never block a run.
            print(
                f"[LOCAL_SCHEDULER] WARNING: Could not delete old per-loader log {old_log.name}: {e}", file=sys.stderr
            )


def _rotate_scheduler_log_if_oversized(log_path: Path) -> None:
    try:
        if not log_path.exists() or log_path.stat().st_size <= _SCHEDULER_LOG_MAX_BYTES:
            return
        rotated = log_path.with_suffix(log_path.suffix + ".1")
        # Keep only one rotated backup - this is a debugging trail, not an audit record
        # (durable audit trail for actual loader runs lives in data_loader_status/
        # logs/load_*.log per-loader files, untouched by this rotation). Same-day file only,
        # so at most one concurrent invocation was writing it before this one started - the
        # Windows open-file-rename failure is still possible here (best-effort, fails open),
        # but now bounded to a single day's worth of spam instead of unbounded history.
        if rotated.exists():
            rotated.unlink()
        log_path.rename(rotated)
        print(
            f"[LOCAL_SCHEDULER] Rotated oversized {log_path.name} (>{_SCHEDULER_LOG_MAX_BYTES // (1024 * 1024)}MB) to {rotated.name}"
        )
    except OSError as e:
        # Best-effort: a rotation failure (e.g. file locked by another concurrent scheduler
        # invocation still writing to it) must never block this run from starting - fall back
        # to appending to the oversized file rather than crashing the whole pipeline over a
        # housekeeping step.
        print(f"[LOCAL_SCHEDULER] WARNING: Could not rotate {log_path.name}: {e}", file=sys.stderr)
