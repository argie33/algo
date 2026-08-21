"""Regression test for the 2026-08-21 "Other" bucket sweep: load_current_reports_8k.py's
"no_8k_filings_in_recent_submissions" was never wired into
lambda/api/routes/scores.py's _COVERAGE_CATEGORY_RULES, so it silently fell through to
"Other (errors / excluded)" - the same silent-fallthrough bug class as
test_scores_coverage_sec_filing_and_analyst_categorization_20260820.py and
test_scores_coverage_unmapped_reason_sweep_20260820.py.

8-Ks are event-driven (executive changes, M&A, material agreements), not periodic - a quiet
filer with none in its recent SEC submissions feed is a real, verifiable fact, not a loader
gap. This was the single largest contributor to "Other (errors / excluded)" on the live
coverage report (1,092 of 2,017 rows, >50%).
"""

import importlib

scores_mod = importlib.import_module("lambda.api.routes.scores")


def test_no_8k_filings_categorizes_as_legitimate():
    assert scores_mod._categorize_reason("no_8k_filings_in_recent_submissions") == "Legitimate / not applicable"
