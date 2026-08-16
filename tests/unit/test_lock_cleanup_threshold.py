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

UPDATED (2026-08-16): superseded again by the Session 98 fix referenced in
_cleanup_expired_locks()'s own docstring ("Use maximum configured loader timeout instead of
hardcoded defaults. Prices timeout is 900 minutes... detecting stuck loaders at 1-2 hours
would force-delete legitimate long-running loader locks mid-execution"). The threshold is now
derived live from loaders/loader_timeout_config.py's per-loader registry
(max(all_timeouts) + 300s grace) instead of a flat 7200s/3600s constant, and no longer branches
on LOCAL_MODE or LOADER_SLA_TIMEOUT_SECONDS at all - both were removed along with the constant
they gated. This file's previous assertions (flat 7200s/3600s, env-var override) were asserting
removed behavior and failing outright (observed threshold: 86700s = "prices" loader's configured
1440min timeout + 300s grace). Rewritten to verify the actual current contract: the threshold
tracks the real registry, not a hardcoded value that goes stale every time a loader's timeout
config changes.
"""

import os
from unittest.mock import MagicMock, patch

from algo.orchestration.orchestrator import Orchestrator
from loaders.loader_timeout_config import get_loader_timeouts


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
    def test_threshold_matches_max_configured_loader_timeout_plus_grace(self):
        """The threshold must be derived from the real per-loader timeout registry (the
        longest-configured loader + 300s grace), not a hardcoded value - so it automatically
        stays correct as individual loader timeouts change, instead of silently drifting out
        of sync the way the flat 7200s constant this replaced did."""
        expected = max(get_loader_timeouts().values()) + 300
        thresholds = _run_cleanup_and_capture_threshold({})
        assert thresholds, "threshold must be passed as a bound SQL parameter, not hardcoded"
        assert all(t == expected for t in thresholds), (
            f"expected threshold to track max(loader_timeout_config) + 300s grace ({expected}s), got {thresholds}"
        )

    def test_long_running_loader_not_flagged_stuck_in_production(self):
        """The core bug: a real loader (insider_transaction_velocity) legitimately still
        running at 702s must NOT be force-deleted/alerted-on - the threshold must be the
        real max-configured-timeout-based value, not a short flat one that would flag any
        long-running loader as crashed."""
        expected = max(get_loader_timeouts().values()) + 300
        cur = MagicMock()
        # fetchall() is wired to always return the same stuck-looking row regardless of the
        # WHERE threshold (this is a unit test of the threshold value, not live SQL
        # filtering) - so the query having asked for the correct threshold is what we assert
        # on below via the alert-query's bound parameter.
        cur.fetchall.return_value = [("insider_transaction_velocity", None, 702.0)]
        cur.rowcount = 0

        class _Ctx:
            def __enter__(self):
                return cur

            def __exit__(self, *a):
                return False

        with patch("algo.orchestration.orchestrator.DatabaseContext", return_value=_Ctx()):
            Orchestrator._cleanup_expired_locks(_fake_self())

        alert_query_call = cur.execute.call_args_list[0]
        assert alert_query_call.args[1][0] == expected, (
            f"the stuck-lock alert query must filter on the real max-configured-timeout "
            f"threshold ({expected}s), not a flat/short value that would flag a "
            f"legitimately-running loader as crashed"
        )
