"""Regression test for the 2026-08-20 unmapped-reason sweep: cross-checked every live
*_unavailable_reason value across the whole schema (112 columns) against
lambda/api/routes/scores.py's _COVERAGE_CATEGORY_RULES to find any that silently fall through
to "Other (errors / excluded)" - the same silent-fallthrough bug class as
test_scores_coverage_sec_filing_and_analyst_categorization_20260820.py. Found 3 with real live
rows that are genuine sanity-check rejections or missing-SEC-data cases, not errors:

- no_companyfacts (loaders/load_dividend_data.py): the companyfacts API response has no
  "facts" key at all - same class as no_us_gaap_facts/no_xbrl_filings - "Missing SEC/XBRL data".
- implausible_dcf_result (loaders/load_value_quality_growth_metrics.py): the DCF model
  produced a per-share value outside MAX_INTRINSIC_VALUE_PER_SHARE bounds (only reached when
  fcf_yield > 0) - "Implausible / rejected value".
- garbage_metric_value_implausible_growth_rate (loaders/load_value_quality_growth_metrics.py,
  RENAMED 2026-08-31 from "garbage_metric_value_abs_gt_100000" - that name had gone stale, still
  describing the pre-2026-08-28 MAX_TREND_PERCENTAGE_POINTS/100000% bound after every site
  setting it had already switched to the tighter MAX_PLAUSIBLE_GROWTH_PCT/2000% one): an
  EPS/earnings growth rate whose magnitude exceeds that bound (a near-zero denominator
  artifact) - "Implausible / rejected value".
"""

import importlib

scores_mod = importlib.import_module("lambda.api.routes.scores")


def test_no_companyfacts_categorizes_as_missing_sec_data():
    assert scores_mod._categorize_reason("no_companyfacts") == "Missing SEC/XBRL data"


def test_dcf_and_growth_sanity_rejections_categorize_as_implausible():
    for reason in ("implausible_dcf_result", "garbage_metric_value_implausible_growth_rate"):
        assert scores_mod._categorize_reason(reason) == "Implausible / rejected value", (
            f"{reason!r} categorized as {scores_mod._categorize_reason(reason)!r}, not 'Implausible / rejected value'"
        )
