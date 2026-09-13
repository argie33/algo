"""Regression test: StalenessChecker's table-level technical_data_daily check couldn't see a
frozen SUBPOPULATION of active symbols whose OWN price_daily data was current.

Third sibling of the frozen-price/frozen-score checks (test_staleness_frozen_price_check_
20260908.py, test_staleness_frozen_symbol_check_20260908.py) - see the goal session that added
this (2026-09-13, "data integrity gaps galore... gaps in our approach"): 136 active symbols
(a cluster of BlackRock closed-end funds - BBN/BCAT/BCX/... - plus ACHV/AFBI/ALOT/AVNS/EFA) had
current price_daily data but technical_data_daily frozen anywhere from 7 days to 5+ weeks stale,
invisible to the table-level MAX(date) check and to coverage.py's aggregate-percentage
threshold check alike - this was the actual driver of a live technical_data_daily/
trend_template_data coverage ERROR (96.0% < 96% threshold).

Routes mocked responses by the rendered SQL text (not a fixed shape) since StalenessChecker.run()
issues many different queries against the same cursor - see
[[watermark_desync_test_fixture_fix_20260907]] for why a fixed-shape mock is unsafe here.
"""

from unittest.mock import MagicMock

from algo.monitoring.data_patrol.checks.staleness import StalenessChecker
from algo.monitoring.data_patrol.config import PatrolConfig


def _cursor_with_frozen_technical_count(frozen_count: int) -> MagicMock:
    cursor = MagicMock()

    def fake_execute(sql, *args, **kwargs):
        cursor._last_sql = sql

    def fake_fetchone():
        if "td.latest_date IS NULL OR td.latest_date <" in cursor._last_sql:
            return (frozen_count,)
        return ("2026-09-13",)

    cursor.execute.side_effect = fake_execute
    cursor.fetchone.side_effect = fake_fetchone
    cursor.fetchall.return_value = []
    return cursor


class TestStalenessFrozenTechnicalCheck:
    def test_flags_warn_when_symbols_are_frozen(self):
        checker = StalenessChecker(PatrolConfig())
        results = checker.run(_cursor_with_frozen_technical_count(40))

        frozen_results = [r for r in results if "frozen_technical_symbol_count" in r.details]
        assert len(frozen_results) == 1
        assert frozen_results[0].severity == "warn"
        assert frozen_results[0].details["frozen_technical_symbol_count"] == 40

    def test_no_warn_when_nothing_is_frozen(self):
        checker = StalenessChecker(PatrolConfig())
        results = checker.run(_cursor_with_frozen_technical_count(0))

        frozen_results = [r for r in results if "frozen_technical_symbol_count" in r.details]
        assert len(frozen_results) == 1
        assert frozen_results[0].severity == "info"
