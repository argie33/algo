"""Regression test for the 2026-08-19 fix (goal session continuation): the coverage
dashboard's "Legitimate / not applicable" bucket was missing "foreign_private_issuer_exempt" -
a reason string load_insider_holdings_sec.py/load_insider_transaction_velocity.py already used
(from a fix that predates this session), but that was never wired into
lambda/api/routes/scores.py's _COVERAGE_CATEGORY_RULES. Every symbol using it silently fell
through to "Other (errors / excluded)" instead. Live-caught on the real dashboard: backfilling
those two loaders' already-correct FPI distinction relabeled 1,052 symbols to this reason, and
the live "Other" total jumped by exactly 1,052 - the same class of gap as the two sibling
"foreign_private_issuer_no_quarterly_filings"/"foreign_private_issuer_no_8k_filings" reasons
this same session already wired in, just for a pre-existing reason string this session's own
new-reason additions didn't cover.

All three represent the identical underlying fact (a foreign private issuer's permanent SEC
reporting exemption, not a data gap more loader coverage could ever close), so this test also
guards them staying together rather than one drifting to a different bucket in a future edit.
"""

import importlib

scores_mod = importlib.import_module("lambda.api.routes.scores")


def test_all_three_foreign_private_issuer_reasons_categorize_as_legitimate():
    for reason in (
        "foreign_private_issuer_exempt",
        "foreign_private_issuer_no_quarterly_filings",
        "foreign_private_issuer_no_8k_filings",
    ):
        assert scores_mod._categorize_reason(reason) == "Legitimate / not applicable", (
            f"{reason!r} categorized as {scores_mod._categorize_reason(reason)!r}, not "
            "'Legitimate / not applicable' - a foreign private issuer's permanent SEC "
            "exemption must never read as a real, fixable data gap."
        )
