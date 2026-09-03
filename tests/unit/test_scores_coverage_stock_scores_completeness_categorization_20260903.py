"""Regression test for the 2026-09-03 synchronous static sweep of
lambda/api/routes/scores.py's _categorize_reason(): stock_scores' own `reason` column - the
final composite-scoring stage - was entirely unmapped.

load_stock_scores.py's `_build_score_row` writes
f"Completeness {pct:.2f}% < {threshold}% threshold (missing metrics: {...})" whenever too
few of the 5 pillars (quality/growth/value/risk/momentum) were available to trust a
composite score. A full sentence with a variable percentage, not a snake_case code, so
`_categorize_reason`'s `base = reason.split(":")[0].strip()` came out as "Completeness NN.NN%
< NN.N% threshold (missing metrics" and never matched any set literal - same shape as the
already-fixed "Insufficient historical data:" sentence. Live-confirmed 227 rows, the largest
unmapped stock_scores reason.

The sibling "Operation failed: {exception}" wrapper (RuntimeError's generic exception-message
wrap) is deliberately NOT caught by the same rule - it can wrap an arbitrary exception, not
always a data-completeness fact, so it correctly falls through to the "Other (errors /
excluded)" default instead of risking a false "just a data gap" label on a real bug.
"""

import importlib

scores_mod = importlib.import_module("lambda.api.routes.scores")


def test_completeness_threshold_sentences_categorize_as_insufficient_history():
    for reason in (
        "Completeness 40.00% < 70.0% threshold (missing metrics: quality, growth, value)",
        "Completeness 60.00% < 70.0% threshold (missing metrics: growth, risk)",
        "Completeness 20.00% < 70.0% threshold (missing metrics: quality, growth, value, risk)",
    ):
        assert scores_mod._categorize_reason(reason) == "Insufficient history", (
            f"{reason!r} categorized as {scores_mod._categorize_reason(reason)!r}, not 'Insufficient history'"
        )


def test_operation_failed_wrapper_not_swept_into_insufficient_history():
    reason = (
        "Operation failed: [STOCK_SCORES] TRBG: CRITICAL - zero metrics available. "
        "Got 0/5 metrics. Cannot compute score with no metric data."
    )
    assert scores_mod._categorize_reason(reason) == "Other (errors / excluded)"
