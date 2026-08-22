"""Regression test (2026-08-22, "Top Causes of Missing Data" Other-bucket sweep):
load_positioning_metrics.py's "missing_finra_data" (per-field marker for "no FINRA
short-interest row on file for this symbol at all") was sitting in "Other (errors /
excluded)" even though it's the same underlying fact as short_interest_finra.reason's
"finra_data_unavailable", already bucketed "Missing SEC/XBRL data" - the FINRA feed
genuinely doesn't cover this issue, not an unexplained error. Live-confirmed: 585 of 712
"Other" rows (82%) were this single reason.
"""

import importlib

scores_mod = importlib.import_module("lambda.api.routes.scores")


def test_missing_finra_data_categorizes_with_finra_data_unavailable():
    assert scores_mod._categorize_reason("missing_finra_data") == "Missing SEC/XBRL data"
    assert scores_mod._categorize_reason("finra_data_unavailable") == "Missing SEC/XBRL data"
