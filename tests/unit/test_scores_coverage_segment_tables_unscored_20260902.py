"""Regression test (2026-09-02, SEC/XBRL missing-data sweep): sec_segment_info/
sec_segment_metrics were never added to _UNSCORED_TABLES despite being whole-table
display-only, same class as positioning_metrics/short_interest_finra (317f7b806/5c74a48e8).
Grepped repo-wide across every scoring loader and found zero references - the only
consumers are lambda/api/routes/market.py and financials.py (informational display
endpoints) plus this file's own coverage report. These two tables alone account for 494
no_segment_dimension_contexts_in_xbrl_xml + 345 no_segment_revenue_in_xbrl_xml (839 raw
rows, scripts/audit_unavailable_reasons.py) that were inflating the "Missing SEC/XBRL data"
headline for gaps that can never move a stock's score.
"""

import importlib

scores_mod = importlib.import_module("lambda.api.routes.scores")


def test_segment_tables_are_unscored():
    assert "sec_segment_info" in scores_mod._UNSCORED_TABLES
    assert "sec_segment_metrics" in scores_mod._UNSCORED_TABLES


def test_previously_unscored_tables_still_present():
    """Regression guard: adding the segment tables must not have replaced the set instead
    of extending it."""
    assert "positioning_metrics" in scores_mod._UNSCORED_TABLES
    assert "short_interest_finra" in scores_mod._UNSCORED_TABLES


def test_scored_factor_tables_not_marked_unscored():
    assert "quality_metrics" not in scores_mod._UNSCORED_TABLES
    assert "growth_metrics" not in scores_mod._UNSCORED_TABLES
    assert "value_metrics" not in scores_mod._UNSCORED_TABLES
