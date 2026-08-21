"""Regression test for the 2026-08-20 "Top Causes of Missing Data" root-cause audit
(goal session): re-ran the live unmapped-reason sweep (scripts/audit_unavailable_reasons.py)
against the current schema and cross-checked every reason string appearing in a column this
report actually scans (lambda/api/routes/scores.py's _get_scores_coverage) against
_COVERAGE_CATEGORY_RULES. Found 3 more silently falling through to "Other (errors / excluded)" -
same bug class as test_scores_coverage_unmapped_reason_sweep_20260820.py, just a later pass:

- eps_scale_mismatch (loaders/load_sec_valuations.py, _sanity_check_pe_ratio): >10x ttm_eps vs
  yfinance mismatch, same per-filing XBRL scale-bug class as shares_outstanding_scale_mismatch -
  "Implausible / rejected value". 35 live rows (sec_valuations.reason).
- zero_total_segment_revenue (utils/external/sec_xbrl_segments.py): every tagged segment's
  revenue is negative (ASC 280 elimination lines, excluded by design) or the reportable total is
  0 - segment XBRL facts exist but aren't usable, same class as the other segment-data reasons
  already in "Missing SEC/XBRL data". 19 live rows (sec_segment_info.reason).
- ad_calculation_failed (loaders/technical_indicators.py's compute_ad_rating via
  loaders/load_positioning_metrics.py): fires only when len(close) < 20 or the recent window is
  all-NaN - despite the name, not a calculation error, the same fact as insufficient_price_history
  on the same column - "Insufficient history". 11 live rows
  (positioning_metrics.ad_rating_unavailable_reason).
"""

import importlib

scores_mod = importlib.import_module("lambda.api.routes.scores")


def test_eps_scale_mismatch_categorizes_as_implausible():
    assert scores_mod._categorize_reason("eps_scale_mismatch") == "Implausible / rejected value"


def test_zero_total_segment_revenue_categorizes_as_missing_sec_data():
    assert scores_mod._categorize_reason("zero_total_segment_revenue") == "Missing SEC/XBRL data"


def test_ad_calculation_failed_categorizes_as_insufficient_history():
    assert scores_mod._categorize_reason("ad_calculation_failed") == "Insufficient history"
