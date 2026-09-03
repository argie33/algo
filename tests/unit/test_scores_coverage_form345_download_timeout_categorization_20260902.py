"""Regression test (2026-09-02, SEC/XBRL missing-data sweep): "Form345_download_timeout" was
sitting in "Other (errors / excluded)" as a bare set literal with no explanation.
utils/external/sec_form345_transaction_velocity_cached.py's CachedForm345Aggregator writes it
directly when a caller's wait_for_download blocks past timeout_seconds waiting on the shared
Form 3/4/5 bulk download - the same "SEC bulk feed didn't come back in time" fact as
sec_form345_bulk_data_unavailable (load_insider_transaction_velocity.py's own except-
TimeoutError path), already bucketed "Missing SEC/XBRL data". Still live-firing (17 rows,
most recent within the last day as of this fix), not stale debris.
"""

import importlib

scores_mod = importlib.import_module("lambda.api.routes.scores")


def test_form345_download_timeout_categorizes_with_bulk_data_unavailable():
    assert scores_mod._categorize_reason("Form345_download_timeout") == "Missing SEC/XBRL data"
    assert scores_mod._categorize_reason("sec_form345_bulk_data_unavailable") == "Missing SEC/XBRL data"
