"""Regression test for the 2026-09-03 synchronous static sweep of
lambda/api/routes/scores.py's _categorize_reason(): insider_transaction_velocity's generic
fallback reason was unmapped.

load_insider_transaction_velocity.py's fetch_incremental() sets
`reason = metrics.reason or "no_data"` when the velocity aggregator marks
data_unavailable=True but supplies no specific reason string - the same "no insider-
transaction coverage for this symbol" fact as its sibling `no_insider_transactions_in_lookback`
(already mapped to "Ownership data unresolved"), just the generic fallback case. Currently 0
live rows but real, reachable code on the same table/column as its sibling.
"""

import importlib

scores_mod = importlib.import_module("lambda.api.routes.scores")


def test_insider_velocity_generic_no_data_categorizes_as_ownership_unresolved():
    assert scores_mod._categorize_reason("no_data") == "Ownership data unresolved"


def test_insider_velocity_specific_lookback_reason_still_categorizes_same_bucket():
    assert scores_mod._categorize_reason("no_insider_transactions_in_lookback") == "Ownership data unresolved"
