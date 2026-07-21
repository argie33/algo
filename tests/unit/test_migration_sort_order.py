"""Regression test for migrations/run.py's migration file ordering.

CRITICAL (2026-07-21 loader-review audit): get_pending_migrations() applies migration
files in sorted order on a fresh database. A plain string sort on the filename breaks at
every digit-count boundary - "1000_x" sorts before "999_y" under str comparison, even
when the 1000-numbered migration's own name says it depends on the 999-numbered one
having already run (see migrations/versions/999_emergency_recreate_positions_view.sql
and migrations/versions/1000_refresh_positions_view_after_creation.sql).
"""

from pathlib import Path

from migrations.run import _migration_sort_key


def test_1000_sorts_after_999():
    files = [
        Path("1000_refresh_positions_view_after_creation.sql"),
        Path("999_emergency_recreate_positions_view.sql"),
    ]
    ordered = sorted(files, key=_migration_sort_key)
    assert ordered[0].name == "999_emergency_recreate_positions_view.sql"
    assert ordered[1].name == "1000_refresh_positions_view_after_creation.sql"


def test_numeric_order_across_all_digit_counts():
    files = [
        Path("1005_fix_closed_trades_missing_status.sql"),
        Path("110_add_unavailable_metrics_to_stock_scores.sql"),
        Path("999_cleanup_orphaned_growth_columns.sql"),
        Path("1000_safety_refresh_positions_view.sql"),
        Path("001_initial_schema.py"),
        Path("94_add_phase7_composite_score_config.sql"),
    ]
    ordered = [f.name for f in sorted(files, key=_migration_sort_key)]
    assert ordered == [
        "001_initial_schema.py",
        "94_add_phase7_composite_score_config.sql",
        "110_add_unavailable_metrics_to_stock_scores.sql",
        "999_cleanup_orphaned_growth_columns.sql",
        "1000_safety_refresh_positions_view.sql",
        "1005_fix_closed_trades_missing_status.sql",
    ]


def test_same_number_ties_break_alphabetically_by_full_stem():
    """Two migrations sharing a version number (e.g. 032_a.py / 032_b.py, a known
    naming collision in migrations/versions/) must still sort deterministically -
    same tie-break as the old plain-stem sort, just with a numeric primary key added."""
    files = [
        Path("032_enforce_safety_thresholds.py"),
        Path("032_add_data_patrol_log_index.py"),
    ]
    ordered = [f.name for f in sorted(files, key=_migration_sort_key)]
    assert ordered == [
        "032_add_data_patrol_log_index.py",
        "032_enforce_safety_thresholds.py",
    ]
