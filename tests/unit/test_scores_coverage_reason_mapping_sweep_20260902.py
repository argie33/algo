"""Regression test (2026-09-02, SEC/XBRL missing-data sweep): cross-checked every distinct
reason string live in the DB (scripts/audit_unavailable_reasons.py --min-count 20 output)
against _categorize_reason() and found several genuinely unmapped, silently falling through
to "Other (errors / excluded)":

- no_recent_free_cash_flow_reported (quality_metrics fcf_yield/fcf_margin/fcf_to_net_income/
  free_cash_flow) - real "no FCF reported recently" SEC-data fact, same class as
  no_recent_balance_sheet_data_reported.
- stale_fiscal_year_not_confirmed_by_full_sec_refetch (quarterly_income_statement, 73 live
  rows) - loaders/helpers/sec_base.py's retraction of a fiscal year a full unfiltered SEC
  refetch no longer reproduces.
- garbage_metric_value_implausible_ratio - sibling of the already-mapped
  garbage_metric_value_implausible_growth_rate, just for non-growth-rate fields.
- momentum_metrics' semicolon-joined "momentum_{period}:insufficient_price_history" reason
  strings - _categorize_reason's base = reason.split(":")[0] comes out as "momentum_3m"/
  "momentum_12m"/etc, never matching the "insufficient_price_history" set member directly.
"""

import importlib

scores_mod = importlib.import_module("lambda.api.routes.scores")


def test_no_recent_free_cash_flow_reported_categorizes_as_missing_sec_xbrl():
    assert scores_mod._categorize_reason("no_recent_free_cash_flow_reported") == "Missing SEC/XBRL data"


def test_stale_fiscal_year_not_confirmed_categorizes_as_missing_sec_xbrl():
    assert (
        scores_mod._categorize_reason("stale_fiscal_year_not_confirmed_by_full_sec_refetch") == "Missing SEC/XBRL data"
    )


def test_fpi_currency_data_rejected_categorizes_as_missing_sec_xbrl():
    assert scores_mod._categorize_reason("fpi_currency_data_rejected") == "Missing SEC/XBRL data"


def test_raw_unconverted_currency_stale_value_categorizes_as_missing_sec_xbrl():
    assert scores_mod._categorize_reason("raw_unconverted_currency_stale_value_20260829") == "Missing SEC/XBRL data"


def test_no_recent_balance_sheet_data_reported_categorizes_as_missing_sec_xbrl():
    assert scores_mod._categorize_reason("no_recent_balance_sheet_data_reported") == "Missing SEC/XBRL data"


def test_garbage_metric_value_implausible_ratio_categorizes_as_implausible():
    assert scores_mod._categorize_reason("garbage_metric_value_implausible_ratio") == "Implausible / rejected value"


def test_momentum_single_period_insufficient_history_categorizes_correctly():
    assert scores_mod._categorize_reason("momentum_12m:insufficient_price_history") == "Insufficient history"


def test_momentum_multi_period_insufficient_history_categorizes_correctly():
    reason = "momentum_3m:insufficient_price_history; momentum_6m:insufficient_price_history; momentum_12m:insufficient_price_history"
    assert scores_mod._categorize_reason(reason) == "Insufficient history"


def test_negative_enterprise_value_categorizes_as_legitimate_not_applicable():
    assert scores_mod._categorize_reason("negative_enterprise_value") == "Legitimate / not applicable"


def test_zero_revenue_reported_this_period_categorizes_as_legitimate_not_applicable():
    assert scores_mod._categorize_reason("zero_revenue_reported_this_period") == "Legitimate / not applicable"
