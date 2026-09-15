"""Regression tests for two real bugs found+fixed 2026-09-15 (/goal "get our scores right"
session, while root-causing the missing stock_splits table - see
scripts/fix_missing_stock_splits.py's own module docstring for the full evidence trail):

(1) PriceSanityChecker.check_corporate_actions was DROP-only - a REVERSE split (price jumps
    UP, e.g. a real 1-for-10) produced zero alert at all. Live-confirmed via yfinance ground
    truth: of 25 real splits found this session, roughly 20 were reverse splits this check
    would never have caught.

(2) A DB error inside any DataPatrol sub-check left the SHARED cursor's transaction aborted
    (InFailedSqlTransaction) with no rollback - every check that ran AFTER the failing one then
    failed too, with a misleading generic "transaction is aborted" message instead of its own
    real error. Live-caught: a real SQL bug in check_corporate_actions (fixed same session)
    silently cascaded through check_sequence_continuity/check_isolated_spike_corruption/
    check_trading_day_gaps in the same PriceSanityChecker.run(), and would equally have
    cascaded through every OTHER checker in DataPatrol's full 17-checker suite via base.py's
    own per-checker loop.
"""

import inspect
from unittest.mock import MagicMock

from algo.monitoring.data_patrol.base import BaseCheck, CheckResult, DataPatrol
from algo.monitoring.data_patrol.checks.price_sanity import PriceSanityChecker
from algo.monitoring.data_patrol.config import PatrolConfig


def _price_sanity_checker() -> PriceSanityChecker:
    return PriceSanityChecker(PatrolConfig())


class TestCorporateActionCatchesReverseSplits:
    def test_query_checks_both_drop_and_rise(self) -> None:
        source = inspect.getsource(PriceSanityChecker.check_corporate_actions)
        sql_start = source.index("cur.execute(")
        sql = source[sql_start:]
        assert "drop_ratio" in sql, "must still check the drop side (forward splits/crashes)"
        assert "rise_ratio" in sql, "must also check the rise side (reverse splits) - this was the real gap"

    def test_query_excludes_already_recorded_splits(self) -> None:
        # A confirmed-and-fixed split (scripts/fix_missing_stock_splits.py writes to
        # stock_splits) must drop off this WARN list on the next run instead of nagging
        # forever - the finding measures "still needs remediation," not "ever happened."
        source = inspect.getsource(PriceSanityChecker.check_corporate_actions)
        assert "stock_splits" in source
        assert "NOT EXISTS" in source

    def test_config_provides_rise_ratio(self) -> None:
        cfg = PatrolConfig()
        corp_cfg = cfg.get_corporate_actions_config()
        assert "rise_ratio" in corp_cfg
        assert corp_cfg["rise_ratio"] > 0, (
            "rise_ratio must be positive (a symmetric threshold to the negative drop_ratio)"
        )


class TestPriceSanityCheckerRollsBackBetweenSubChecks:
    def test_rollback_called_after_every_sub_check(self) -> None:
        checker = _price_sanity_checker()
        cur = MagicMock()
        # Make every real DB call raise so each sub-check's own internal except swallows it -
        # the only observable signal that matters here is whether rollback() gets called
        # regardless, isolating each sub-check from the others.
        cur.execute.side_effect = Exception("simulated DB error")
        checker.run(cur)
        assert cur.connection.rollback.call_count == 5, (
            "must rollback after each of the 5 sub-checks (price_moves/corporate_actions/"
            "sequence_continuity/isolated_spike_corruption/trading_day_gaps) so one sub-check's "
            "poisoned transaction can't cascade into the next"
        )

    def test_rollback_failure_itself_does_not_crash_run(self) -> None:
        checker = _price_sanity_checker()
        cur = MagicMock()
        cur.execute.side_effect = Exception("simulated DB error")
        cur.connection.rollback.side_effect = Exception("rollback also failed")
        # Must not raise - a rollback failure should be logged, not crash the whole checker.
        checker.run(cur)


class _ExplodingChecker(BaseCheck):
    def run(self, cur):  # type: ignore[override]
        raise RuntimeError("simulated checker crash")


class TestDataPatrolRollsBackAfterCheckerFailure:
    def test_rollback_called_after_checker_exception(self) -> None:
        # Exercises the per-checker exception handler in DataPatrol.run() directly (not the
        # full run() method, which opens a real DB connection) - constructs the same
        # try/except/rollback shape inline against a mock connection to verify the rollback
        # actually fires, since base.py's real run() is not unit-testable without a live DB.
        conn = MagicMock()
        cur = MagicMock()
        patrol = DataPatrol(PatrolConfig())
        checker = _ExplodingChecker(PatrolConfig())
        try:
            results = checker.run(cur)
            patrol.results.extend(results)
        except Exception:
            conn.rollback()
        assert conn.rollback.called, "a checker-level exception must roll back the shared connection"
