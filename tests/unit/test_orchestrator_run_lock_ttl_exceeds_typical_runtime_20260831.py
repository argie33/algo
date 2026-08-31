"""Regression test: the orchestrator's own distributed run-lock must have a TTL longer than
a real orchestrator run actually takes.

Bug found 2026-08-31: `algo/orchestration/orchestrator.py`'s `Orchestrator.__init__` called
`get_lock_manager()` with no arguments, so it used that factory's own default
`lock_duration_seconds=300` (Session 107 lowered it from 600s for faster crashed-loader-lock
cleanup - a change scoped to loader locks, not the orchestrator's own run lock). But
`_acquire_run_lock()`'s own docstring documents "Orchestrator runs typically take 470+
seconds" - LONGER than the lock's 300s TTL.

That mismatch means during every normal (non-crashed) run, the lock's DynamoDB `expires_at`
timestamp passes while the run is still actively executing (around Phase 6-8, when real trades
get submitted) - `DynamoDBLockManager.acquire()`'s conditional write
(`attribute_not_exists(#expires_at) OR #expires_at < :now`) would let ANY concurrent acquire()
attempt from that point until release succeed, believing the lock free, even though the
original instance is still alive and trading. A manual re-trigger, an EventBridge Scheduler
retry, or a second invocation started unaware one is already running would then run
CONCURRENTLY against the same live Alpaca account and database - duplicate orders, corrupted
portfolio state. This is exactly the scenario Session 282's fail-closed fix (same file, "ALWAYS
fail closed when DynamoDB locks unavailable") was written to prevent, but that fix only covers
the lock backend being unreachable, not the TTL being shorter than a real run.

Fixed by passing an explicit `lock_duration_seconds=1800` (30 min - a large safety margin over
the documented ~470s typical runtime) at the one call site that creates the orchestrator's own
run-lock manager.

This is a static-pattern regression test (not a construction/execution test) because
Orchestrator.__init__ is a large constructor with many heavy dependencies (DB, AlertManager,
execution tracker) - matching the established convention elsewhere in this codebase for
enforcing an exact source pattern that's impractical to exercise via full instantiation.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
ORCHESTRATOR_PY = REPO_ROOT / "algo" / "orchestration" / "orchestrator.py"

# The typical-runtime figure the orchestrator's own code documents (_acquire_run_lock's
# docstring: "Orchestrator runs typically take 470+ seconds"). The lock TTL must exceed this
# with real margin, not just barely clear it.
DOCUMENTED_TYPICAL_RUNTIME_SECONDS = 470


def _orchestrator_source() -> str:
    return ORCHESTRATOR_PY.read_text(encoding="utf-8")


def test_run_lock_manager_passes_explicit_duration_not_the_bare_default():
    """The bug: `get_lock_manager()` with no arguments silently uses a 300s default shorter
    than a real run. The fix must pass lock_duration_seconds explicitly at construction."""
    source = _orchestrator_source()
    match = re.search(r"self\.lock_manager\s*=\s*get_lock_manager\(([^)]*)\)", source)
    assert match, "expected to find self.lock_manager = get_lock_manager(...) in orchestrator.py"
    assert "lock_duration_seconds" in match.group(1), (
        "self.lock_manager = get_lock_manager() must pass an explicit lock_duration_seconds - "
        "the bare default (300s) is shorter than a real orchestrator run (~470s+ typical), "
        "letting a concurrent run's acquire() succeed while the original is still trading."
    )


def test_run_lock_ttl_has_real_safety_margin_over_typical_runtime():
    """Not just "longer than 470s" - long enough that normal runtime variance (retries,
    backoff, slow API calls) can't eat the margin away to nothing."""
    source = _orchestrator_source()
    match = re.search(r"self\.lock_manager\s*=\s*get_lock_manager\(lock_duration_seconds=(\d+)\)", source)
    assert match, "expected self.lock_manager = get_lock_manager(lock_duration_seconds=<N>)"
    configured_ttl = int(match.group(1))
    assert configured_ttl >= DOCUMENTED_TYPICAL_RUNTIME_SECONDS * 2, (
        f"orchestrator run-lock TTL ({configured_ttl}s) does not have at least 2x safety margin "
        f"over the documented typical runtime ({DOCUMENTED_TYPICAL_RUNTIME_SECONDS}s) - a run "
        f"that's merely slower than average (retries, backoff, a slow Alpaca API call), not "
        f"even crashed, could still let the lock look expired while genuinely still running."
    )
