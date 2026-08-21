"""Regression test: the dashboard's "Loader Health: healthy" / "READY TO TRADE" / per-row
"ok" status badges must not read as an all-clear when the same data actually has a real
NULL-rate or coverage problem.

Bug (live user-reported 2026-08-21): "Loader Health: All loaders healthy" and "READY TO TRADE"
are computed purely from job-EXECUTION success (data_loader_status) and table AGE/halt-flag
(market.py's ready_to_trade = data_fresh_enough and not trading_halted) - neither one looks at
freshness_enhancements.py's separate NULL-ratio/coverage checks. A table can show a green
"ok"/✓ row here while the very same response's "Data Quality Issues"/"Coverage Gaps" sections
(built from data_quality_issues/quality_status/coverage_status on the SAME item dicts) list a
real problem for it - e.g. trend_template_data showing "✓ ok" in the freshness table while
weinstein_stage was 11% NULL. Fixed by having _build_loader_health_section, the READY TO TRADE
line, the compact-panel badge, and the per-table row icon in _build_freshness_panel all check
quality_status/coverage_status too, instead of only the freshness `st` field.
"""

from dashboard.panels.health import (
    _build_freshness_panel,
    _build_loader_health_section,
    _format_health_data_fresh_section,
)
from tests.test_helpers.assertions import render_panel_to_text


def _flatten(text: str) -> str:
    return " ".join(text.split())


class TestLoaderHealthSectionReflectsQualityIssues:
    def test_all_executions_healthy_but_quality_issue_present_is_not_a_bare_all_clear(self):
        hlth_items = [
            {
                "tbl": "trend_template_data",
                "quality_status": "error",
                "data_quality_issues": ["weinstein_stage: 11.0% NULL"],
            },
            {"tbl": "price_daily", "quality_status": "ok"},
        ]
        rows = _build_loader_health_section([], total_unhealthy=0, total_tracked=47, hlth_items=hlth_items)
        text = _flatten(" ".join(r.plain if hasattr(r, "plain") else "" for r in rows))

        assert "All loaders healthy" not in text
        assert "1 with data quality issues" in text

    def test_no_quality_or_coverage_issues_keeps_original_all_clear_message(self):
        hlth_items = [{"tbl": "price_daily", "quality_status": "ok", "coverage_status": "complete"}]
        rows = _build_loader_health_section([], total_unhealthy=0, total_tracked=1, hlth_items=hlth_items)
        text = _flatten(" ".join(r.plain if hasattr(r, "plain") else "" for r in rows))

        assert "All loaders healthy" in text

    def test_coverage_gap_also_counted_separately_from_quality(self):
        hlth_items = [{"tbl": "technical_data_daily", "coverage_status": "sparse"}]
        rows = _build_loader_health_section([], total_unhealthy=0, total_tracked=1, hlth_items=hlth_items)
        text = _flatten(" ".join(r.plain if hasattr(r, "plain") else "" for r in rows))

        assert "1 with coverage gaps" in text


class TestReadyToTradeCaveatsOnKnownIssues:
    def test_ready_to_trade_true_with_quality_issue_gets_caveat(self):
        items = [
            {
                "tbl": "price_daily",
                "st": "ok",
                "role": "CRIT",
                "age_hours": 1,
                "row_count": 100,
                "quality_status": "ok",
            },
            {
                "tbl": "trend_template_data",
                "st": "ok",
                "role": "IMP",
                "age_hours": 1,
                "row_count": 100,
                "quality_status": "error",
                "data_quality_issues": ["weinstein_stage: 11.0% NULL"],
            },
        ]
        panel = _build_freshness_panel(items, ready_to_trade=True, hlth_dict={})
        text = _flatten(render_panel_to_text(panel))

        assert "READY TO TRADE" in text
        assert "quality issue" in text

    def test_ready_to_trade_true_with_no_known_issues_has_no_caveat(self):
        items = [
            {"tbl": "price_daily", "st": "ok", "role": "CRIT", "age_hours": 1, "row_count": 100, "quality_status": "ok"}
        ]
        panel = _build_freshness_panel(items, ready_to_trade=True, hlth_dict={})
        text = _flatten(render_panel_to_text(panel))

        assert "READY TO TRADE" in text
        assert "issue" not in text.lower()


class TestPerRowIconReflectsQualityIssueEvenWhenFresh:
    def test_fresh_table_with_quality_issue_does_not_render_bare_ok(self):
        items = [
            {
                "tbl": "trend_template_data",
                "st": "ok",
                "role": "IMP",
                "age_hours": 1,
                "row_count": 100,
                "quality_status": "error",
                "data_quality_issues": ["weinstein_stage: 11.0% NULL (threshold 5%, latest date)"],
            }
        ]
        panel = _build_freshness_panel(items, ready_to_trade=True, hlth_dict={})
        text = _flatten(render_panel_to_text(panel))

        assert "QA" in text
        assert "⚠" in text

    def test_fresh_table_with_no_quality_issue_still_renders_ok(self):
        items = [
            {"tbl": "price_daily", "st": "ok", "role": "CRIT", "age_hours": 1, "row_count": 100, "quality_status": "ok"}
        ]
        panel = _build_freshness_panel(items, ready_to_trade=True, hlth_dict={})
        text = _flatten(render_panel_to_text(panel))

        assert "ok" in text.lower()
        assert "QA" not in text


class TestCompactBadgeReflectsQualityIssues:
    def test_compact_ready_to_trade_badge_flags_issue_count(self):
        hlth_list = [
            {"tbl": "price_daily", "quality_status": "ok", "age_hours": 1.0},
            {"tbl": "trend_template_data", "quality_status": "error", "age_hours": 1.0},
            {"tbl": "buy_sell_daily", "coverage_status": "sparse", "age_hours": 1.0},
        ]
        result = _format_health_data_fresh_section(hlth_list, crit=[], ready_to_trade=True, ages=[1.0, 1.0, 1.0])

        assert "READY TO TRADE" in result
        assert "2 data issue(s)" in result

    def test_compact_ready_to_trade_badge_clean_when_no_issues(self):
        hlth_list = [{"tbl": "price_daily", "quality_status": "ok", "coverage_status": "complete", "age_hours": 1.0}]
        result = _format_health_data_fresh_section(hlth_list, crit=[], ready_to_trade=True, ages=[1.0])

        assert "READY TO TRADE" in result
        assert "data issue" not in result
