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


# ADDED 2026-09-02 (same goal session, static sweep): cross-checked every reason-string
# literal in the SEC/XBRL loader files against this map (not just live DB counts, which
# can't see a reason string that hasn't fired yet) and found 9 more genuinely unmapped
# strings falling to "Other (errors / excluded)".


def test_no_recent_operating_cash_flow_reported_categorizes_as_missing_sec_xbrl():
    assert scores_mod._categorize_reason("no_recent_operating_cash_flow_reported") == "Missing SEC/XBRL data"


def test_entity_name_not_found_categorizes_as_missing_sec_xbrl():
    assert scores_mod._categorize_reason("entity_name_not_found") == "Missing SEC/XBRL data"


def test_submissions_not_found_404_categorizes_as_missing_sec_xbrl():
    assert scores_mod._categorize_reason("submissions_not_found_404") == "Missing SEC/XBRL data"


def test_submissions_empty_categorizes_as_missing_sec_xbrl():
    assert scores_mod._categorize_reason("submissions_empty") == "Missing SEC/XBRL data"


def test_no_submissions_categorizes_as_missing_sec_xbrl():
    assert scores_mod._categorize_reason("no_submissions") == "Missing SEC/XBRL data"


def test_stockholders_equity_never_tagged_in_filings_categorizes_as_missing_sec_xbrl():
    assert scores_mod._categorize_reason("stockholders_equity_never_tagged_in_filings") == "Missing SEC/XBRL data"


def test_total_liabilities_not_reported_categorizes_as_missing_sec_xbrl():
    assert scores_mod._categorize_reason("total_liabilities_not_reported") == "Missing SEC/XBRL data"


def test_insufficient_year_over_year_quarterly_history_categorizes_as_insufficient_history():
    assert scores_mod._categorize_reason("insufficient_year_over_year_quarterly_history") == "Insufficient history"


def test_implausibly_low_forward_pe_categorizes_as_implausible():
    assert scores_mod._categorize_reason("implausibly_low_forward_pe") == "Implausible / rejected value"


# ADDED 2026-09-02 (same goal session, broader suffix-pattern sweep): 5 more genuinely
# unmapped strings found via a wider net (any quoted string ending in a "reason-like" suffix
# like _unavailable/_missing/_not_found, not just the narrower first-pass pattern).


def test_filings_key_missing_categorizes_as_missing_sec_xbrl():
    assert scores_mod._categorize_reason("filings_key_missing") == "Missing SEC/XBRL data"


def test_recent_filings_key_missing_categorizes_as_missing_sec_xbrl():
    assert scores_mod._categorize_reason("recent_filings_key_missing") == "Missing SEC/XBRL data"


def test_sec_form345_bulk_data_unavailable_categorizes_as_missing_sec_xbrl():
    assert scores_mod._categorize_reason("sec_form345_bulk_data_unavailable") == "Missing SEC/XBRL data"


def test_filing_date_unavailable_categorizes_as_missing_sec_xbrl():
    assert scores_mod._categorize_reason("filing_date_unavailable") == "Missing SEC/XBRL data"


def test_segment_data_unavailable_categorizes_as_missing_sec_xbrl():
    assert scores_mod._categorize_reason("segment_data_unavailable") == "Missing SEC/XBRL data"


# ADDED 2026-09-02 (same goal session, static sweep continuation restricted to strings
# actually assigned inside a "*_unavailable_reason" ternary block in the loader, not just any
# quoted snake_case literal): no_sec_valuations_row - total_cash/cash_per_share/ebitda's own
# "sec_valuations has no row at all for this symbol" fact, landed 2026-09-02 08:20 CDT
# (commits 1547b826c/37fc38252) but never wired into this map.


def test_no_sec_valuations_row_categorizes_as_missing_sec_xbrl():
    assert scores_mod._categorize_reason("no_sec_valuations_row") == "Missing SEC/XBRL data"
