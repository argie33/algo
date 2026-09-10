"""Regression test: StalenessChecker's table-level price_daily check couldn't see a frozen
SUBPOPULATION of active symbols.

Sibling gap to the stock_scores frozen-symbol check
(test_staleness_frozen_symbol_check_20260908.py) - see
price_daily_stale_symbol_cohort_backfilled_20260906 in memory: 107-115 active symbols sat
10-20+ days stale in price_daily (closed-end funds plus liquid names like AVB/LEG) while the
table-level MAX(date) check stayed "fresh" the whole time, since most of the table kept
updating normally. That session flagged the per-symbol gap as unfixed; this test pins the fix.

Routes mocked responses by the rendered SQL text (not a fixed shape) since StalenessChecker.run()
issues many different queries against the same cursor - see
[[watermark_desync_test_fixture_fix_20260907]] for why a fixed-shape mock is unsafe here.
"""

from unittest.mock import MagicMock

from algo.monitoring.data_patrol.checks.staleness import StalenessChecker
from algo.monitoring.data_patrol.config import PatrolConfig


def _cursor_with_frozen_price_count(frozen_count: int) -> MagicMock:
    cursor = MagicMock()

    def fake_execute(sql, *args, **kwargs):
        cursor._last_sql = sql

    def fake_fetchone():
        if "pd.latest_date <" in cursor._last_sql:
            return (frozen_count,)
        return ("2026-09-08",)

    cursor.execute.side_effect = fake_execute
    cursor.fetchone.side_effect = fake_fetchone
    cursor.fetchall.return_value = []
    return cursor


class TestStalenessFrozenPriceCheck:
    def test_flags_warn_when_symbols_are_frozen(self):
        checker = StalenessChecker(PatrolConfig())
        results = checker.run(_cursor_with_frozen_price_count(112))

        frozen_results = [r for r in results if "frozen_price_symbol_count" in r.details]
        assert len(frozen_results) == 1
        assert frozen_results[0].severity == "warn"
        assert frozen_results[0].details["frozen_price_symbol_count"] == 112

    def test_no_warn_when_nothing_is_frozen(self):
        checker = StalenessChecker(PatrolConfig())
        results = checker.run(_cursor_with_frozen_price_count(0))

        frozen_results = [r for r in results if "frozen_price_symbol_count" in r.details]
        assert len(frozen_results) == 1
        assert frozen_results[0].severity == "info"
