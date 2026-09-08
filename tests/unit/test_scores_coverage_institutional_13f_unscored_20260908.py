"""Regression test (2026-09-08, /goal score-sanity/coverage audit): institutional_holdings_13f was
never added to _UNSCORED_TABLES despite being whole-table display-only, same class as
positioning_metrics/short_interest_finra (both already unscored since Positioning's retirement).
Grepped load_stock_scores.py repo-wide and found zero references to institutional_ownership_pct
or this table. Concretely this miscategorized ~1,647 rows where
"institutional_ownership_pct_capped_raw_ratio_exceeded_100pct" is set alongside a REAL, populated
institutional_ownership_pct value (just capped at 100%) as a scored-factor gap landing in
"Other (errors / excluded)" (no bucket maps that reason string).
"""

import importlib

scores_mod = importlib.import_module("lambda.api.routes.scores")


def test_institutional_holdings_13f_is_unscored():
    assert "institutional_holdings_13f" in scores_mod._UNSCORED_TABLES


def test_previously_unscored_tables_still_present():
    """Regression guard: adding institutional_holdings_13f must not have replaced the set
    instead of extending it."""
    assert "positioning_metrics" in scores_mod._UNSCORED_TABLES
    assert "short_interest_finra" in scores_mod._UNSCORED_TABLES
    assert "sec_segment_info" in scores_mod._UNSCORED_TABLES
    assert "sec_segment_metrics" in scores_mod._UNSCORED_TABLES


def test_scored_factor_tables_not_marked_unscored():
    assert "quality_metrics" not in scores_mod._UNSCORED_TABLES
    assert "growth_metrics" not in scores_mod._UNSCORED_TABLES
    assert "value_metrics" not in scores_mod._UNSCORED_TABLES
