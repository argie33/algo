"""Regression test (2026-09-08, /goal score-sanity sweep): two more reason literals were
falling through to "Other (errors / excluded)" for lack of a mapping.

- utils/loaders/exception_handler.py's generic exception-classification handlers
  (timeout_retryable/connection_error/rate_limit_or_service_unavailable/api_schema_mismatch/
  data_invalid/no_data_found), called by handle_exception() from load_sec_valuations.py,
  load_sec_segment_metrics.py, load_earnings_calendar_sec.py, load_company_info_sec.py, and
  loaders/helpers/sec_base.py on real TimeoutError/ConnectionError/HTTPError(429,503)/
  KeyError/ValueError/no-results outcomes - the same operational-error class as
  fetch_error:ValueError/unable to fetch after retries already in "Other (errors / excluded)".
- utils/external/sec_form345_transaction_velocity_cached.py's "Form345_download_in_progress"
  (the shared Form 3/4/5 bulk download still in flight, not yet timed out) - same fact as its
  sibling "Form345_download_timeout" (see test_scores_coverage_form345_download_timeout_
  categorization_20260902.py), already bucketed "Missing SEC/XBRL data".
"""

import importlib

scores_mod = importlib.import_module("lambda.api.routes.scores")


def test_exception_handler_generic_reasons_categorize_as_other():
    for reason in (
        "timeout_retryable",
        "connection_error",
        "rate_limit_or_service_unavailable",
        "api_schema_mismatch",
        "data_invalid",
        "no_data_found",
    ):
        assert scores_mod._categorize_reason(reason) == "Other (errors / excluded)", (
            f"{reason!r} categorized as {scores_mod._categorize_reason(reason)!r}, not 'Other (errors / excluded)'"
        )


def test_form345_download_in_progress_categorizes_with_its_timeout_sibling():
    assert scores_mod._categorize_reason("Form345_download_in_progress") == "Missing SEC/XBRL data"
