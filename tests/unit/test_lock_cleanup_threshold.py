"""Regression test for the 2026-07-27 fix: Orchestrator._cleanup_expired_locks() used a flat,
hardcoded 600-second (10-minute) threshold to force-DELETE loader locks regardless of
environment, completely disconnected from utils/optimal_loader.py's own per-loader lock_ttl
(600s in LOCAL_MODE, 7200s in production - because real loader runtimes are 60-90+ min for
price_daily, ~15 min for insider_transaction_velocity). In production this meant the
orchestrator's own preflight check would strip a still-legitimately-running loader's lock
after just 10 minutes and let a concurrent trigger acquire it and double-write - exactly the
race the lock exists to prevent.

Live-reproduced 2026-07-27: a real dry-run flagged insider_transaction_velocity's lock as
"crash suspected" at 702s into its known-normal ~900s run.

Fixed to mirror optimal_loader.py's own LOCAL_MODE-aware threshold (600s local, else
LOADER_SLA_TIMEOUT_SECONDS/7200s) instead of an independent, shorter, hardcoded value.

UPDATED (2026-07-28): optimal_loader.py's own LOCAL_MODE threshold moved from a flat 600s to
3600s, since real local dev runs regularly exceed 600s (institutional_holdings_13f held its
lock 926.6s on an ordinary run; cash-flow statement backfills observed at ~2385s - an interim
1800s value still undercut that observed run, so it was raised again to 3600s for real margin).
This test file's local-mode expectation is updated to 3600s to keep mirroring that value, per
this same file's own stated purpose.
"""

import os
from unittest.mock import MagicMock, patch

from algo.orchestration.orchestrator import Orchestrator


def _fake_self():
    return object.__new__(Orchestrator)


def _run_cleanup_and_capture_threshold(env: dict) -> list:
    """Runs _cleanup_expired_locks under the given env and returns the threshold value(s)
    actually bound into the SQL executed against the DB (empty list if none was ever
    parameterized - i.e. pre-fix hardcoded-in-SQL-text behavior)."""
    cur = MagicMock()
    cur.fetchall.return_value = []
    cur.rowcount = 0

    class _Ctx:
        def __enter__(self):
            return cur

        def __exit__(self, *a):
            return False

    with (
        patch.dict(os.environ, env, clear=False),
        patch("algo.orchestration.orchestrator.DatabaseContext", return_value=_Ctx()),
    ):
        Orchestrator._cleanup_expired_locks(_fake_self())

    thresholds = []
    for call in cur.execute.call_args_list:
        args = call.args
        if len(args) > 1 and args[1]:
            thresholds.extend(v for v in args[1] if isinstance(v, int))
    return thresholds


class TestLockCleanupThresholdMatchesLoaderTTL:
    def test_production_threshold_matches_optimal_loader_default_sla(self):
        """In production (LOCAL_MODE unset/false), the cleanup threshold must match
        optimal_loader.py's default lock_ttl of 7200s, not a shorter hardcoded value that
        would delete a still-running loader's lock out from under it."""
        thresholds = _run_cleanup_and_capture_threshold({"LOCAL_MODE": "False"})
        assert thresholds, "threshold must be passed as a bound SQL parameter, not hardcoded"
        assert all(t == 7200 for t in thresholds), (
            f"expected production threshold of 7200s (matches optimal_loader.py's lock_ttl), got {thresholds}"
        )

    def test_production_threshold_honors_loader_sla_env_override(self):
        """Threshold must track LOADER_SLA_TIMEOUT_SECONDS the same way optimal_loader.py's
        lock_ttl does, not be a value independent of it."""
        thresholds = _run_cleanup_and_capture_threshold({"LOCAL_MODE": "False", "LOADER_SLA_TIMEOUT_SECONDS": "3600"})
        assert thresholds and all(t == 3600 for t in thresholds)

    def test_local_mode_threshold_matches_optimal_loader_3600s(self):
        """LOCAL_MODE threshold must mirror optimal_loader.py's own is_local_mode lock_ttl
        (3600s, not the old 600s - real local dev runs regularly exceed 600s, and even
        exceed an interim 1800s value: cash-flow statement backfills observed at ~2385s)."""
        thresholds = _run_cleanup_and_capture_threshold({"LOCAL_MODE": "True"})
        assert thresholds and all(t == 3600 for t in thresholds)

    def test_local_mode_threshold_honors_loader_sla_env_override(self):
        """Even in LOCAL_MODE, an explicit LOADER_SLA_TIMEOUT_SECONDS must win - this was
        the other half of the original bug: LOCAL_MODE used to ignore this env var entirely."""
        thresholds = _run_cleanup_and_capture_threshold({"LOCAL_MODE": "True", "LOADER_SLA_TIMEOUT_SECONDS": "300"})
        assert thresholds and all(t == 300 for t in thresholds)

    def test_long_running_loader_not_flagged_stuck_in_production(self):
        """The core bug: a real loader (insider_transaction_velocity) legitimately still
        running at 702s must NOT be force-deleted/alerted-on in production, where the SLA
        threshold is 7200s."""
        cur = MagicMock()
        cur.fetchall.return_value = [("insider_transaction_velocity", None, 702.0)]
        cur.rowcount = 0

        class _Ctx:
            def __enter__(self):
                return cur

            def __exit__(self, *a):
                return False

        with (
            patch.dict(os.environ, {"LOCAL_MODE": "False"}, clear=False),
            patch("algo.orchestration.orchestrator.DatabaseContext", return_value=_Ctx()),
        ):
            # fetchall() is wired to always return the same stuck-looking row regardless of
            # the WHERE threshold (this is a unit test of the threshold value, not live SQL
            # filtering) - so the query having asked for the correct (7200s) threshold is
            # what we assert on below via the alert-query's bound parameter.
            Orchestrator._cleanup_expired_locks(_fake_self())

        alert_query_call = cur.execute.call_args_list[0]
        assert alert_query_call.args[1][0] == 7200, (
            "the stuck-lock alert query must filter on the production SLA threshold (7200s), "
            "not a flat 600s that would flag a legitimately-running loader as crashed"
        )
