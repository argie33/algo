"""Regression test for the 2026-08-20 fix: the coverage dashboard's "Implausible / rejected
value" bucket was missing "shares_outstanding_scale_mismatch" - the reason string
load_sec_valuations.py's market_cap sanity check (>10x vs yfinance) writes when it rejects a
mis-scaled shares_outstanding, the same class of rejection as the sibling
"shares_outstanding_invalid" reason already in this bucket. load_short_interest_finra.py
already excludes symbols carrying this reason (its own 2026-08-20 fix), but
lambda/api/routes/scores.py's _COVERAGE_CATEGORY_RULES never had it added, so every affected
row (live: ~79-87 symbols x 9 reason columns) fell through to "Other (errors / excluded)"
instead - the same silent-fallthrough bug class as
test_scores_coverage_foreign_private_issuer_categorization.py's foreign-private-issuer reasons.
"""

import importlib

scores_mod = importlib.import_module("lambda.api.routes.scores")


def test_shares_outstanding_scale_mismatch_categorizes_as_implausible():
    for reason in ("shares_outstanding_invalid", "shares_outstanding_scale_mismatch", "implausible_ratio"):
        assert scores_mod._categorize_reason(reason) == "Implausible / rejected value", (
            f"{reason!r} categorized as {scores_mod._categorize_reason(reason)!r}, not "
            "'Implausible / rejected value' - a rejected/mis-scaled value must never read as "
            "an unexplained 'Other' error."
        )
