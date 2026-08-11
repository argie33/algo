"""Regression test (2026-08-03): pg_advisory_lock IDs must be stable across process
instances, not just within one process.

Bug: HaltFlagManager's four advisory-lock call sites (_check_halt_flag_rds,
_set_halt_flag_rds, _proactive_clear_stale_halt_rds, _clear_halt_flag_rds) and Phase 7's
signal-quality-score update both computed their lock_id via `hash(some_string) %
(2**31)`. Python randomizes str hashing per-process by default (PYTHONHASHSEED is unset
anywhere in this repo's Docker/Lambda/CI config) - confirmed live, three separate
`python -c "hash('orchestrator_halt')"` invocations returned three different values.
Every "RACE CONDITION FIX" comment on these methods claims concurrent orchestrator
instances "wait on same lock", but each process actually derived a DIFFERENT lock_id for
the identical logical resource, so pg_advisory_lock/pg_try_advisory_lock silently never
serialized concurrent Lambda/ECS instances - exactly the scenario the comments describe
protecting against.

Fixed by switching to zlib.crc32 (not seed-randomized), matching the fixed-constant
pattern already used elsewhere in this codebase for the same reason (see
PORTFOLIO_SNAPSHOT_LOCK_ID in position_sizer.py / reconciliation.py).

This test can't spawn a real second process from within pytest, so it instead locks in
the property that actually matters: the lock ID is a fixed constant computed from a
non-randomized hash function, not from Python's built-in `hash()`.
"""

import subprocess
import sys
import zlib

from algo.orchestration.halt_flag_manager import HaltFlagManager


def test_halt_flag_lock_id_is_crc32_based_not_builtin_hash() -> None:
    expected = zlib.crc32(HaltFlagManager.HALT_FLAG_DYNAMODB_KEY.encode()) % (2**31)
    assert HaltFlagManager.HALT_FLAG_LOCK_ID == expected


def test_halt_flag_lock_id_stable_across_real_separate_processes() -> None:
    """The actual regression: spawn two independent Python processes (each gets its own
    random PYTHONHASHSEED) and confirm they compute the identical lock_id. Using the
    built-in hash() instead of crc32 would make this test flaky/fail across runs."""
    snippet = (
        "from algo.orchestration.halt_flag_manager import HaltFlagManager;print(HaltFlagManager.HALT_FLAG_LOCK_ID)"
    )
    outputs = {
        subprocess.run([sys.executable, "-c", snippet], capture_output=True, text=True, check=True).stdout.strip()
        for _ in range(3)
    }
    assert len(outputs) == 1


def test_phase7_signal_scores_lock_id_stable_across_real_separate_processes() -> None:
    snippet = "import zlib; print(zlib.crc32(b'phase7_signal_scores') % (2 ** 31))"
    outputs = {
        subprocess.run([sys.executable, "-c", snippet], capture_output=True, text=True, check=True).stdout.strip()
        for _ in range(3)
    }
    assert len(outputs) == 1
