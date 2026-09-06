"""Regression test (2026-08-22, "Top Causes of Missing Data" Other-bucket sweep):
load_positioning_metrics.py's "missing_finra_data" (per-field marker for "no FINRA
short-interest row on file for this symbol at all") was sitting in "Other (errors /
excluded)" even though it's the same underlying fact as short_interest_finra.reason's
"finra_data_unavailable" - the FINRA feed genuinely doesn't cover this issue, not an
unexplained error. Live-confirmed: 585 of 712 "Other" rows (82%) were this single reason.

MOVED 2026-09-06 (goal: "get Missing SEC/XBRL to zero the right way" sweep): both reasons
(plus sibling "finra_api_unreachable") relocated from "Missing SEC/XBRL data" to "Ownership
data unresolved" - FINRA short-interest settlement data is a wholly separate feed from SEC
EDGAR/XBRL (load_short_interest_finra.py never touches SEC filings), so bucketing it as
"SEC/XBRL" inflated that headline with rows no XBRL fix could ever close. Still not "Other"
- this test's original assertion (not miscategorized as an unexplained error) still holds,
just against the corrected bucket.
"""

import importlib

scores_mod = importlib.import_module("lambda.api.routes.scores")


def test_missing_finra_data_categorizes_with_finra_data_unavailable():
    assert scores_mod._categorize_reason("missing_finra_data") == "Ownership data unresolved"
    assert scores_mod._categorize_reason("finra_data_unavailable") == "Ownership data unresolved"
