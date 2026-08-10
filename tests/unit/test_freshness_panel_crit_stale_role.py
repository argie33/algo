"""Regression test: DATA FRESHNESS panel's "CRIT STALE" banner must only list
role="CRIT" tables, not every non-"ok" table regardless of role.

Bug: _build_freshness_panel built its "crit_stale" list from `st != "ok"` alone,
ignoring the "role" field the API already computes per table (CRIT/IMP/NORM -
see dashboard/fetchers_config.py). That meant known-non-critical,
not-always-populated tables (e.g. equity_curve_daily, algo_untracked_positions)
triggered the same red "⚠ CRIT STALE" alarm as an actually-critical table like
price_daily, producing misleading TRIGGERED/NOT READY-looking alarms even when
trading was otherwise fine.
"""

from dashboard.panels.health import _build_freshness_panel
from tests.test_helpers.assertions import render_panel_to_text


def test_crit_stale_banner_excludes_non_critical_stale_tables():
    items = [
        {"tbl": "price_daily", "st": "stale", "role": "CRIT", "age_hours": 48, "row_count": 100},
        {"tbl": "equity_curve_daily", "st": "empty", "role": "IMP", "age_hours": None, "row_count": 0},
        {"tbl": "algo_untracked_positions", "st": "empty", "role": "NORM", "age_hours": None, "row_count": 0},
    ]

    panel = _build_freshness_panel(items, ready_to_trade=False)
    text = render_panel_to_text(panel)

    assert "CRIT STALE" in text
    assert "price_daily" in text
    assert "equity_curve_daily" not in text.split("CRIT STALE")[1].split("\n")[0]
    assert "algo_untracked_positions" not in text.split("CRIT STALE")[1].split("\n")[0]


def test_no_crit_stale_banner_when_only_non_critical_tables_stale():
    items = [
        {"tbl": "equity_curve_daily", "st": "empty", "role": "IMP", "age_hours": None, "row_count": 0},
        {"tbl": "algo_untracked_positions", "st": "empty", "role": "NORM", "age_hours": None, "row_count": 0},
    ]

    panel = _build_freshness_panel(items, ready_to_trade=True)
    text = render_panel_to_text(panel)

    assert "CRIT STALE" not in text
