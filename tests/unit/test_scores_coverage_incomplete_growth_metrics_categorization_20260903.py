"""Regression test (2026-09-03, SEC/XBRL missing-data sweep, static unmapped-reason sweep):
"Incomplete growth metrics: ..." was sitting in "Other (errors / excluded)" - a full sentence,
not a snake_case code, so `_categorize_reason`'s `base = reason.split(":")[0]` never matched any
set literal. load_value_quality_growth_metrics.py builds this exact sentence
(f"Incomplete growth metrics: {failed_fields} failed to compute (insufficient history or invalid
data)") for the PARTIAL growth-period-failure case (1-5 of 6 periods failed) - same "not enough
fiscal years on file yet" fact as the already-correctly-bucketed "Insufficient historical data:"
sibling for the ALL-6-periods-failed case. 3,467 live rows affected.
"""

import importlib

scores_mod = importlib.import_module("lambda.api.routes.scores")


def test_incomplete_growth_metrics_categorizes_as_insufficient_history():
    reason = "Incomplete growth metrics: eps_growth_5y, revenue_growth_5y failed to compute (insufficient history or invalid data)"
    assert scores_mod._categorize_reason(reason) == "Insufficient history"


def test_insufficient_historical_data_sibling_still_categorizes_correctly():
    reason = "Insufficient historical data: eps_growth_1y, eps_growth_3y could not be computed"
    assert scores_mod._categorize_reason(reason) == "Insufficient history"
