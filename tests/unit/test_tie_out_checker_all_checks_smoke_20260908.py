"""Smoke test: every check registered in TieOutChecker.run() must execute without crashing.

Found (goal session score-sanity/tie-out sweep, 2026-09-08): TieOutChecker.run() calls ~53
individual check_* methods (algo/monitoring/data_patrol/checks/tie_out.py), but
test_tie_out_checker_20260906.py only covers 3 of them (balance sheet identity, cash flow
identity, EPS reconciliation) with real assertions on flagging logic. The other ~50 checks
have ZERO test coverage that runs in CI - `.github/workflows/ci.yml` never runs the full
DataPatrol suite (it needs a live, loaded production-shaped database; GitHub Actions CI has
none), so a check that references a renamed/dropped column, has a Python-level bug in its own
row-processing, or otherwise crashes at runtime would go undetected until it broke a real
`python algo/algo_data_patrol.py` run in production/local dev - not caught by `pytest tests/`.

This test does NOT replace real per-check logic tests (see test_tie_out_checker_20260906.py
for the model to follow when adding one for a specific check) - it only guarantees every
registered check can execute end-to-end against a cursor that returns zero rows for every
query, catching crashes (AttributeError, NameError, wrong-arity SQL/format-string
mismatches, etc.) that a syntax-level lint pass can't. All 53 checks use cur.fetchall()
exclusively (verified via grep, no cur.fetchone() calls), so a single fetchall-only mock
covers every one of them.
"""

from unittest.mock import MagicMock

from algo.monitoring.data_patrol.checks.tie_out import TieOutChecker
from algo.monitoring.data_patrol.config import INFO, PatrolConfig


def test_every_registered_check_runs_without_crashing_on_empty_result_set() -> None:
    cur = MagicMock()
    cur.fetchall.return_value = []

    checker = TieOutChecker(PatrolConfig())
    results = checker.run(cur)

    # FIXED 2026-09-10: the nonnegative-magnitude checks (Round 7, and the pre-existing Round 5
    # ones sharing their now-fixed shared helper - see tie_out_shared.py's
    # _check_nonnegative_cashflow_field docstring) log an INFO result even when clean, so a
    # zero-row run no longer yields an empty results list overall - it must yield ONLY INFO
    # (never WARN/ERROR/CRIT) since nothing was actually flagged.
    assert all(r.severity == INFO for r in results), "zero rows returned -> no check should flag a violation"
    # Guards against a future refactor accidentally dropping calls out of run() - the count
    # ratchets up as new checks are added, so this only needs bumping when checks are ADDED,
    # never a false failure from unrelated changes.
    assert cur.execute.call_count >= 85, (
        f"expected TieOutChecker.run() to issue at least 85 queries (one or more per "
        f"registered check), got {cur.execute.call_count} - a check may have been silently "
        "dropped from run()'s call list"
    )
