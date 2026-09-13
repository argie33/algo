"""Regression test: StalenessChecker's table-level trend_template_data check couldn't see a
frozen SUBPOPULATION of active symbols whose OWN price_daily data was current.

Fourth sibling of the frozen-price/frozen-score/frozen-technical checks (see
test_staleness_frozen_technical_check_20260913.py for the full evidence trail this mirrors) -
same session, live-checked 2026-09-13: 40 active symbols had current price_daily data but
trend_template_data frozen more than 7 days behind their own price watermark, the same
population size as the technical_data_daily gap fixed earlier this session (consistent with a
shared upstream root cause).

Routes mocked responses by the rendered SQL text (not a fixed shape) since StalenessChecker.run()
issues many different queries against the same cursor - see
[[watermark_desync_test_fixture_fix_20260907]] for why a fixed-shape mock is unsafe here.
"""

from unittest.mock import MagicMock

from algo.monitoring.data_patrol.checks.staleness import StalenessChecker
from algo.monitoring.data_patrol.config import PatrolConfig


def _cursor_with_frozen_trend_count(frozen_count: int) -> MagicMock:
    cursor = MagicMock()

    def fake_execute(sql, *args, **kwargs):
        cursor._last_sql = sql

    def fake_fetchone():
        if "tt.latest_date IS NULL OR tt.latest_date <" in cursor._last_sql:
            return (frozen_count,)
        return ("2026-09-13",)

    cursor.execute.side_effect = fake_execute
    cursor.fetchone.side_effect = fake_fetchone
    cursor.fetchall.return_value = []
    return cursor


class TestStalenessFrozenTrendTemplateCheck:
    def test_flags_warn_when_symbols_are_frozen(self):
        checker = StalenessChecker(PatrolConfig())
        results = checker.run(_cursor_with_frozen_trend_count(40))

        frozen_results = [r for r in results if "frozen_trend_template_symbol_count" in r.details]
        assert len(frozen_results) == 1
        assert frozen_results[0].severity == "warn"
        assert frozen_results[0].details["frozen_trend_template_symbol_count"] == 40

    def test_no_warn_when_nothing_is_frozen(self):
        checker = StalenessChecker(PatrolConfig())
        results = checker.run(_cursor_with_frozen_trend_count(0))

        frozen_results = [r for r in results if "frozen_trend_template_symbol_count" in r.details]
        assert len(frozen_results) == 1
        assert frozen_results[0].severity == "info"
