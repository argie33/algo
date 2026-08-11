"""Regression test for the 2026-08-11 fix: data_patrol's coverage/quality/alignment/
specialized checkers used `isinstance(row, dict)` to validate rows from `DatabaseContext`'s
DictCursor - but `psycopg2.extras.DictRow` (what DictCursor actually returns) is dict-LIKE
(supports .get()/.keys()/item access) and is NOT a `dict` subclass. `isinstance(row, dict)`
was therefore always False for a correctly-configured cursor, so CoverageChecker,
QualityChecker, and AlignmentChecker unconditionally crashed with a misleadingly-worded
"cursor configuration mismatch" TypeError on every single real row - found by actually
running `algo/algo_data_patrol.py --quick` end-to-end against real local data (this ECS-task
entrypoint is genuinely deployed via terraform/modules/pipeline/main.tf, not orphaned tooling,
so this was a real, previously-undetected production bug).

specialized.py:206 already had the correct pattern (`isinstance(row, dict) or
hasattr(row, "keys")`) - all other instances (coverage.py, quality.py, alignment.py x2,
specialized.py x4 more) fixed to match.
"""

from psycopg2.extras import DictRow

from algo.monitoring.data_patrol.checks.coverage import CoverageChecker
from algo.monitoring.data_patrol.config import PatrolConfig


def _make_dict_row(mapping: dict) -> DictRow:
    """Build a real psycopg2.extras.DictRow, the same dict-like-but-not-dict type
    DictCursor actually returns, rather than mocking it."""

    class _Cur:
        description = [(k,) for k in mapping]
        index = {k: i for i, k in enumerate(mapping)}

    row = DictRow(_Cur())
    for i, v in enumerate(mapping.values()):
        row[i] = v
    return row


class TestDataPatrolDictRowNotDictSubclass:
    def test_dictrow_is_not_a_dict_subclass_sanity_check(self):
        """Confirms the actual root cause: DictRow really isn't a dict subclass."""
        row = _make_dict_row({"today_count": 42})
        assert not isinstance(row, dict)
        assert row.get("today_count") == 42

    def test_coverage_checker_accepts_real_dictrow_not_just_dict(self):
        checker = CoverageChecker(config=PatrolConfig())
        row = _make_dict_row({"today_count": 100})

        class _FakeCur:
            def execute(self, *a, **kw):
                pass

            def fetchone(self):
                return row

        # Must not raise TypeError("Expected dict-like row from DictCursor...") - the
        # exact crash this fix resolves.
        checker.check_universe_coverage(_FakeCur())
