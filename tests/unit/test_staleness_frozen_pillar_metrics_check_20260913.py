"""Regression test: momentum_metrics/value_metrics/quality_metrics/growth_metrics had no
per-symbol frozen-or-missing coverage at all in StalenessChecker, unlike price_daily/
stock_scores (see test_staleness_frozen_price_check_20260908.py and
test_staleness_frozen_symbol_check_20260908.py for those siblings).

Live-confirmed on the local DB before this fix (2026-09-13, goal session "data integrity
gaps galore... gaps in our approach"): momentum_metrics had 34 active symbols frozen >7d and
92 with zero row at all; value_metrics/quality_metrics each had 90 missing; growth_metrics
(despite already having a table-level staleness check) had 2 frozen + 90 missing - proof the
table-level MAX(updated_at) check alone was never enough for any of these four single-row-
per-symbol pillar-input tables. This test pins the generalized fix.

EXTENDED (same session, immediately after landing the four above): stability_metrics (a real,
current Risk-pillar scoring input written by loaders/load_risk_metrics_daily.py) and
positioning_metrics (no longer a scoring input since 2026-08-27, but still live-queried by the
scores API's positioning_inputs field) are the same ON CONFLICT (symbol) shape and were missed
by the first pass. Live-confirmed: stability_metrics had 133 active symbols with zero row at
all; positioning_metrics had 37 frozen >7d behind and 101 with zero row.
"""

from unittest.mock import MagicMock

from algo.monitoring.data_patrol.checks.staleness import StalenessChecker
from algo.monitoring.data_patrol.config import PatrolConfig


def _cursor_with_pillar_counts(frozen_missing_by_table: dict) -> MagicMock:
    cursor = MagicMock()

    def fake_execute(sql, *args, **kwargs):
        cursor._last_sql = sql

    def fake_fetchone():
        sql = cursor._last_sql
        if "FILTER (" in sql and "missing_count" in sql:
            for table, (frozen, missing) in frozen_missing_by_table.items():
                if f"LEFT JOIN {table} t" in sql:
                    return (frozen, missing)
            return (0, 0)
        if "pd.latest_date <" in sql:
            return (0,)
        if "ss.date <" in sql:
            return (0,)
        return ("2026-09-12",)

    cursor.execute.side_effect = fake_execute
    cursor.fetchone.side_effect = fake_fetchone
    cursor.fetchall.return_value = []
    return cursor


class TestStalenessFrozenPillarMetricsCheck:
    def test_flags_warn_when_symbols_are_frozen_or_missing(self):
        cursor = _cursor_with_pillar_counts(
            {
                "momentum_metrics": (34, 92),
                "value_metrics": (2, 90),
                "quality_metrics": (0, 90),
                "growth_metrics": (2, 90),
                "stability_metrics": (0, 133),
                "positioning_metrics": (37, 101),
            }
        )
        checker = StalenessChecker(PatrolConfig())
        results = checker.run(cursor)

        by_table = {r.target_table: r for r in results if "missing_symbol_count" in r.details}
        assert set(by_table) == {
            "momentum_metrics",
            "value_metrics",
            "quality_metrics",
            "growth_metrics",
            "stability_metrics",
            "positioning_metrics",
        }

        assert by_table["momentum_metrics"].severity == "warn"
        assert by_table["momentum_metrics"].details["frozen_symbol_count"] == 34
        assert by_table["momentum_metrics"].details["missing_symbol_count"] == 92

        assert by_table["quality_metrics"].severity == "warn"
        assert by_table["quality_metrics"].details["frozen_symbol_count"] == 0
        assert by_table["quality_metrics"].details["missing_symbol_count"] == 90

        assert by_table["stability_metrics"].severity == "warn"
        assert by_table["stability_metrics"].details["frozen_symbol_count"] == 0
        assert by_table["stability_metrics"].details["missing_symbol_count"] == 133

        assert by_table["positioning_metrics"].severity == "warn"
        assert by_table["positioning_metrics"].details["frozen_symbol_count"] == 37
        assert by_table["positioning_metrics"].details["missing_symbol_count"] == 101

    def test_no_warn_when_nothing_is_frozen_or_missing(self):
        cursor = _cursor_with_pillar_counts(
            {
                "momentum_metrics": (0, 0),
                "value_metrics": (0, 0),
                "quality_metrics": (0, 0),
                "growth_metrics": (0, 0),
                "stability_metrics": (0, 0),
                "positioning_metrics": (0, 0),
            }
        )
        checker = StalenessChecker(PatrolConfig())
        results = checker.run(cursor)

        by_table = {r.target_table: r for r in results if "missing_symbol_count" in r.details}
        assert set(by_table) == {
            "momentum_metrics",
            "value_metrics",
            "quality_metrics",
            "growth_metrics",
            "stability_metrics",
            "positioning_metrics",
        }
        for r in by_table.values():
            assert r.severity == "info"
