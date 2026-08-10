"""Regression tests for DATA FRESHNESS - EXPANDED panel loader/table diagnostics.

data_loader_status.status (NOT_STARTED/RUNNING/COMPLETED/FAILED/TIMEOUT, see
utils/loaders/status_enum.py) and stale_threshold_days are written/computed by the
backend but were previously dropped before reaching _build_freshness_panel - a
loader that has literally never run looked identical to one that ran and produced
zero rows, and a TIMEOUT looked identical to a FAILED. Separately, /api/admin/inventory
(untracked/missing tables) was never consumed by the dashboard at all.
"""

from dashboard.panels.health import _build_freshness_panel
from tests.test_helpers.assertions import render_panel_to_text


def test_never_started_loader_shown_separately_from_empty():
    items = [
        {"tbl": "price_daily", "st": "ok", "role": "CRIT", "age": 0.1, "row_count": 100},
        {
            "tbl": "insider_transaction_velocity",
            "st": "empty",
            "role": "NORM",
            "age": None,
            "row_count": 0,
            "loader_run_status": "NOT_STARTED",
        },
    ]

    panel = _build_freshness_panel(items, ready_to_trade=True)
    text = render_panel_to_text(panel)

    assert "Never run:" in text
    assert "insider_transaction_velocity" in text.split("Never run:")[1].split("\n")[0]


def test_timeout_and_failed_are_distinguishable_in_loader_errors():
    items = [
        {
            "tbl": "sec_valuations",
            "st": "stale",
            "role": "NORM",
            "age": 5,
            "row_count": 10,
            "loader_error": "Connection reset",
            "loader_run_status": "TIMEOUT",
        },
        {
            "tbl": "dividend_data",
            "st": "stale",
            "role": "NORM",
            "age": 5,
            "row_count": 10,
            "loader_error": "401 Unauthorized",
            "loader_run_status": "FAILED",
        },
    ]

    panel = _build_freshness_panel(items, ready_to_trade=True)
    text = render_panel_to_text(panel)

    assert "[TIMEOUT]" in text
    assert "[FAILED]" in text
    # Each tag must be attached to its own table's line in the "Loader errors:" detail
    # section, not swapped. The per-table freshness table above also renders both table
    # names (without a tag), so restrict the search to the error-detail section.
    error_section = text.split("Loader errors:")[1]
    timeout_line = next(line for line in error_section.split("\n") if "sec_valuations" in line)
    failed_line = next(line for line in error_section.split("\n") if "dividend_data" in line)
    assert "[TIMEOUT]" in timeout_line
    assert "[FAILED]" in failed_line


def test_stale_detail_shows_age_vs_own_threshold():
    items = [
        {
            "tbl": "earnings_calendar_sec",
            "st": "stale",
            "role": "NORM",
            "age": 9,
            "row_count": 50,
            "stale_threshold_days": 7,
        },
    ]

    panel = _build_freshness_panel(items, ready_to_trade=True)
    text = render_panel_to_text(panel)

    assert "Stale detail" in text
    assert "9d old, threshold 7d" in text


def test_inventory_untracked_and_missing_tables_shown():
    items = [
        {"tbl": "price_daily", "st": "ok", "role": "CRIT", "age": 0.1, "row_count": 100},
    ]
    inventory = {
        "untracked_tables": ["some_orphaned_table"],
        "missing_tables": ["a_dropped_table"],
    }

    panel = _build_freshness_panel(items, ready_to_trade=True, inventory=inventory)
    text = render_panel_to_text(panel)

    assert "Untracked tables" in text
    assert "some_orphaned_table" in text
    assert "Tracked but missing from DB" in text
    assert "a_dropped_table" in text


def test_inventory_omitted_does_not_break_panel():
    """inventory is optional - callers that never fetch it must still get a valid panel."""
    items = [
        {"tbl": "price_daily", "st": "ok", "role": "CRIT", "age": 0.1, "row_count": 100},
    ]

    panel = _build_freshness_panel(items, ready_to_trade=True)
    text = render_panel_to_text(panel)

    assert "Untracked tables" not in text
    assert "Tracked but missing from DB" not in text


def test_repeated_failures_section_shows_streak_and_last_success(): # migration 1163
    items = [
        {
            "tbl": "sec_valuations",
            "st": "stale",
            "role": "NORM",
            "age": 5,
            "row_count": 10,
            "consecutive_failures": 4,
            "last_success_at": "2026-07-20T09:00:00+00:00",
        },
        {
            "tbl": "dividend_data",
            "st": "stale",
            "role": "NORM",
            "age": 5,
            "row_count": 10,
            "consecutive_failures": 1,  # below the >=2 threshold - must NOT appear
        },
    ]

    panel = _build_freshness_panel(items, ready_to_trade=True)
    text = render_panel_to_text(panel)

    assert "Repeated failures:" in text
    section = text.split("Repeated failures:")[1]
    assert "sec_valuations" in section
    assert "4x in a row" in section
    assert "dividend_data" not in section


def test_repeated_failures_never_succeeded_shown_when_no_last_success():
    items = [
        {
            "tbl": "never_worked_table",
            "st": "empty",
            "role": "NORM",
            "age": None,
            "row_count": 0,
            "consecutive_failures": 3,
            "last_success_at": None,
        },
    ]

    panel = _build_freshness_panel(items, ready_to_trade=True)
    text = render_panel_to_text(panel)

    assert "never succeeded" in text


def test_inventory_error_marker_does_not_break_panel():
    items = [
        {"tbl": "price_daily", "st": "ok", "role": "CRIT", "age": 0.1, "row_count": 100},
    ]

    panel = _build_freshness_panel(items, ready_to_trade=True, inventory={"_error": "timeout"})
    text = render_panel_to_text(panel)

    assert "Untracked tables" not in text
