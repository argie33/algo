"""Regression test for the 2026-08-21 coverage-categorization follow-up to the
beta_unavailable_reason genericization fix (see
tests/unit/test_beta_unavailable_reason_specificity_20260821.py): once
RiskMetricsLoader started writing _get_beta_from_db's real reason instead of the old
hardcoded "missing_price_data", those real reason strings needed wiring into
lambda/api/routes/scores.py's _COVERAGE_CATEGORY_RULES or they'd fall through to
"Other (errors / excluded)" exactly like the old generic string did.
"""

import importlib

scores_mod = importlib.import_module("lambda.api.routes.scores")


def test_beta_history_shortfalls_categorize_as_insufficient_history():
    for reason in (
        "spy_price_data_insufficient: 3/5 days",
        "insufficient_common_dates: 2/5",
        "insufficient_returns: 3/4",
        "insufficient_price_history",
    ):
        assert scores_mod._categorize_reason(reason) == "Insufficient history", (
            f"{reason!r} categorized as {scores_mod._categorize_reason(reason)!r}, not 'Insufficient history'"
        )


def test_extreme_beta_categorizes_as_implausible():
    assert scores_mod._categorize_reason("extreme_beta: 14.20") == "Implausible / rejected value"
