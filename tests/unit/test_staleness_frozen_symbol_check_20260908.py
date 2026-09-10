"""Regression test: StalenessChecker's table-level stock_scores check couldn't see a
frozen SUBPOPULATION of active symbols.

Live-caught (goal session score-sanity sweep, 2026-09-08): utils/loaders/helpers.py's
get_active_symbols() excluded 29 BDCs (MAIN, HTGC, GAIN, TSLX, ...) from every metrics/scores
loader since 2026-09-03, freezing their stock_scores rows permanently while `ss.active` stayed
true. The existing MAX(updated_at)-across-the-whole-table staleness check stayed "fresh"
throughout because most of the table kept updating normally - only a per-symbol check could
have caught it. Routes mocked responses by the rendered SQL text (not a fixed shape) since
StalenessChecker.run() issues many different queries against the same cursor - a shared,
fixed-shape mock would silently answer every query the same way regardless of which table it
was actually for, same trap already documented in
[[watermark_desync_test_fixture_fix_20260907]].
"""

from unittest.mock import MagicMock

from algo.monitoring.data_patrol.checks.staleness import StalenessChecker
from algo.monitoring.data_patrol.config import PatrolConfig


def _cursor_with_frozen_count(frozen_count: int) -> MagicMock:
    cursor = MagicMock()

    def fake_execute(sql, *args, **kwargs):
        cursor._last_sql = sql

    def fake_fetchone():
        if "ss.date <" in cursor._last_sql:
            return (frozen_count,)
        return ("2026-09-08",)

    cursor.execute.side_effect = fake_execute
    cursor.fetchone.side_effect = fake_fetchone
    cursor.fetchall.return_value = []
    return cursor


class TestStalenessFrozenSymbolCheck:
    def test_flags_warn_when_symbols_are_frozen(self):
        checker = StalenessChecker(PatrolConfig())
        results = checker.run(_cursor_with_frozen_count(29))

        frozen_results = [r for r in results if "frozen_symbol_count" in r.details]
        assert len(frozen_results) == 1
        assert frozen_results[0].severity == "warn"
        assert frozen_results[0].details["frozen_symbol_count"] == 29

    def test_no_warn_when_nothing_is_frozen(self):
        checker = StalenessChecker(PatrolConfig())
        results = checker.run(_cursor_with_frozen_count(0))

        frozen_results = [r for r in results if "frozen_symbol_count" in r.details]
        assert len(frozen_results) == 1
        assert frozen_results[0].severity == "info"
