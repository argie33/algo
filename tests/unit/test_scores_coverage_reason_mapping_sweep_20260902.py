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


def test_revenue_absent_from_anchor_year_categorizes_as_missing_sec_xbrl():
    assert scores_mod._categorize_reason("revenue_absent_from_anchor_year") == "Missing SEC/XBRL data"


# ADDED 2026-09-02 (same goal session, later same-day sweep): a second live cross-check
# (scripts/audit_unavailable_reasons.py --min-count 10) found four MORE unmapped reasons
# falling to "Other (errors / excluded)" - all four were themselves added by earlier fixes
# in this same session (roe/roa/net_margin/sustainable_growth_rate/asset_turnover/pe_ratio/
# peg_ratio/fcf_yield's "never tagged in any recent filing" gates) but never wired into this
# map, so the 286 live rows using them got the exact same "Other" fate this whole file is
# about - see _COVERAGE_CATEGORY_RULES's own comment on these four for the full context.


def test_net_income_not_reported_categorizes_as_missing_sec_xbrl():
    assert scores_mod._categorize_reason("net_income_not_reported") == "Missing SEC/XBRL data"


def test_no_recent_total_assets_reported_categorizes_as_missing_sec_xbrl():
    assert scores_mod._categorize_reason("no_recent_total_assets_reported") == "Missing SEC/XBRL data"


def test_eps_never_tagged_in_filings_categorizes_as_missing_sec_xbrl():
    assert scores_mod._categorize_reason("eps_never_tagged_in_filings") == "Missing SEC/XBRL data"


def test_capex_never_tagged_in_recent_filings_categorizes_as_missing_sec_xbrl():
    assert scores_mod._categorize_reason("capex_never_tagged_in_recent_filings") == "Missing SEC/XBRL data"


# ADDED 2026-09-02 (same goal session, quality_row_db anchor-year investigation): the
# balance-sheet-anchored quality_row_db query joins its current-year income-statement
# columns via an EXACT fiscal_year match - when that specific anchor year's own
# annual_income_statement row is unavailable (e.g. a current in-progress fiscal-year
# placeholder) but the symbol has real net_income in a nearby year, roe/roa/net_margin/
# sustainable_growth_rate all fell to generic "missing_sec_data" even though neither
# no-recent nor never-tagged net_income gate applied (both correctly see the real
# nearby-year data). New net_income_absent_from_anchor_year reason (sibling of the
# revenue_absent_from_anchor_year fix landed earlier this session) makes that honest -
# live-confirmed OBX/FTW/XLAB and 342 active-universe symbols total.


def test_net_income_absent_from_anchor_year_categorizes_as_missing_sec_xbrl():
    assert scores_mod._categorize_reason("net_income_absent_from_anchor_year") == "Missing SEC/XBRL data"


# ADDED 2026-09-02 (same goal session, continuation of the anchor-year sweep): operating_
# cash_flow/free_cash_flow siblings - same bug class, affecting accruals_ratio/
# fcf_to_net_income/ocf_to_net_income/operating_cash_flow/free_cash_flow_unavailable_reason.


def test_operating_cash_flow_absent_from_anchor_year_categorizes_as_missing_sec_xbrl():
    assert scores_mod._categorize_reason("operating_cash_flow_absent_from_anchor_year") == "Missing SEC/XBRL data"


def test_free_cash_flow_absent_from_anchor_year_categorizes_as_missing_sec_xbrl():
    assert scores_mod._categorize_reason("free_cash_flow_absent_from_anchor_year") == "Missing SEC/XBRL data"
