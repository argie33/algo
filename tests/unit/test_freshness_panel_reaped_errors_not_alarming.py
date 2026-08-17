"""Regression test: the freshness panel's "loader(s) with errors" line must not treat
abandoned-process reap artifacts the same as a genuinely broken loader.

Bug (live-confirmed 2026-08-16): market.py's loaders_with_errors summary counted every
loader with consecutive_failures >= 1, with no distinction for *why* it failed. Cross-checked
against the live DB while investigating an operator's "dashboard says errors but everything's
actually fine" report: every single one of the 20 flagged loaders had failed purely because
reap_stale_running_loaders() marked an abandoned (no owning process alive) run FAILED with an
"[REAPED]"/"[MANUAL REAP" error_message - not a real bug. local_loader_scheduler.py's
run_pipeline() already treats this exact pattern as self-healing (see its is_reaped_only
check), so these loaders retry and recover on their own - but the dashboard summary still
read "20 loader(s) with errors" in red, indistinguishable from a genuinely broken loader.

market.py now splits loaders_with_errors_genuine / loaders_with_errors_reaped_only into the
summary; this test pins that _build_freshness_panel surfaces that split instead of flattening
it back into one alarming count.
"""

from dashboard.panels.health import _build_freshness_panel
from tests.test_helpers.assertions import render_panel_to_text


def _flatten(text: str) -> str:
    """Collapse whitespace/newlines so assertions survive the 80-col Rich word-wrap
    render_panel_to_text pins to - a long phrase like "(4 reaped, self-healing)" can wrap
    mid-phrase at that width even though it's one contiguous span in the actual markup."""
    return " ".join(text.split())


def _hlth_dict(loaders_with_errors, total_failures, genuine, reaped_only):
    return {
        "summary": {
            "loaders_with_errors": loaders_with_errors,
            "total_loader_failures": total_failures,
            "loaders_with_errors_genuine": genuine,
            "loaders_with_errors_reaped_only": reaped_only,
        }
    }


def test_reaped_only_errors_are_labeled_self_healing_not_red_alert():
    items = [{"tbl": "price_daily", "st": "ok", "role": "CRIT", "age_hours": 1, "row_count": 100}]
    hlth_dict = _hlth_dict(loaders_with_errors=4, total_failures=4, genuine=0, reaped_only=4)

    panel = _build_freshness_panel(items, ready_to_trade=True, hlth_dict=hlth_dict)
    text = _flatten(render_panel_to_text(panel))

    assert "0 loader(s) with errors" in text
    assert "4 reaped, self-healing" in text


def test_genuine_errors_still_shown_prominently():
    items = [{"tbl": "price_daily", "st": "ok", "role": "CRIT", "age_hours": 1, "row_count": 100}]
    hlth_dict = _hlth_dict(loaders_with_errors=2, total_failures=5, genuine=2, reaped_only=0)

    panel = _build_freshness_panel(items, ready_to_trade=True, hlth_dict=hlth_dict)
    text = _flatten(render_panel_to_text(panel))

    assert "2 loader(s) with errors (5 total)" in text
    assert "self-healing" not in text


def test_mixed_genuine_and_reaped_shows_both():
    items = [{"tbl": "price_daily", "st": "ok", "role": "CRIT", "age_hours": 1, "row_count": 100}]
    hlth_dict = _hlth_dict(loaders_with_errors=5, total_failures=6, genuine=1, reaped_only=4)

    panel = _build_freshness_panel(items, ready_to_trade=True, hlth_dict=hlth_dict)
    text = _flatten(render_panel_to_text(panel))

    assert "1 loader(s) with errors (6 total)" in text
    assert "4 reaped, self-healing" in text


def test_missing_split_keys_falls_back_to_treating_all_as_genuine():
    """Older cached API responses won't have the new summary keys - must not crash, and
    must degrade to the pre-fix behavior (all counted as genuine) rather than silently
    hiding real errors."""
    items = [{"tbl": "price_daily", "st": "ok", "role": "CRIT", "age_hours": 1, "row_count": 100}]
    hlth_dict = {"summary": {"loaders_with_errors": 3, "total_loader_failures": 3}}

    panel = _build_freshness_panel(items, ready_to_trade=True, hlth_dict=hlth_dict)
    text = _flatten(render_panel_to_text(panel))

    assert "3 loader(s) with errors (3 total)" in text
    assert "self-healing" not in text
