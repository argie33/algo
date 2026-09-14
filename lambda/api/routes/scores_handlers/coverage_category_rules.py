"""Root-cause categorization rulebook for the /api/scores/coverage report.

Split 2026-09-05 (file-size-ratchet compliance split of coverage.py) - pure data, no logic:
the `_COVERAGE_CATEGORY_RULES` mapping (every known `*_unavailable_reason` literal bucketed
into one of a handful of root-cause categories) plus the fixed display order derived from it.
`_categorize_reason()`, which consumes this table, lives in the sibling
coverage_classification.py (kept separate purely so this data-only file - already the largest
single piece by far, almost entirely inline evidence comments per bucket - didn't also have to
carry the function and push the file over the size cap on its own).
"""

from __future__ import annotations

# Root-cause buckets for /api/scores/coverage. Order is fixed (drives the fixed color
# assignment on the frontend) - every *_unavailable_reason value seen across the schema
# must resolve to exactly one of these via _categorize_reason(), falling back to
# "Other (errors / excluded)". Mirrors the categorization scripts/audit_unavailable_reasons.py
# output was manually bucketed into for the 2026-08-19 "Scores Data Coverage" report.
_COVERAGE_CATEGORY_RULES: list[tuple[str, set[str]]] = [
    (
        "Missing SEC/XBRL data",
        {
            "missing_sec_data",
            "missing_cash_flow_data",
            "total_debt_not_itemized",
            "interest_expense_not_itemized",
            "stockholders_equity_not_reported",
            # ADDED 2026-09-04 (goal session: "Top Causes of Missing Data" sweep): same
            # "the filer never itemizes this XBRL concept" class as total_debt_not_itemized/
            # interest_expense_not_itemized above - written by roic_pct/roce_pct/ebitda_margin/
            # operating_margin/interest_coverage/operating_profitability/ebitda/ebitda_ev's
            # own _get_no_recent_operating_income_symbols()/_get_never_tagged_operating_income_
            # symbols() gates (see their 2026-09-03 "Missing SEC/XBRL data reduction" fix
            # comments throughout load_value_quality_growth_metrics.py) but never added to this
            # map, so every row fell through to "Other (errors / excluded)" instead (32 live scored roce_pct
            # rows, plus unscored siblings on roic_pct/ebitda_margin/interest_coverage/
            # operating_profitability/operating_margin/ebitda).
            "operating_income_not_itemized",
            "no_dividend_xbrl_concepts",
            "no_us_gaap_facts",
            "cik_not_found",
            "depreciation_amortization_not_loaded",
            "ebitda_not_extracted",
            # FIXED 2026-08-19 (goal: "no SEC data" audit, same-day follow-up to the
            # bare_reason_tables extension above): reason strings from the newly-included
            # tables (sec_segment_info/metrics, sec_valuations, short_interest_finra) that
            # didn't exist in this map before because those tables were entirely invisible
            # to this report until now.
            "no_segment_dimension_contexts_in_xbrl_xml",
            "no_segment_revenue_in_xbrl_xml",
            "no_segment_disclosure",
            "no_computable_segment_metrics",
            "no_segment_data",
            "no_segment_count_facts_in_companyfacts",
            "income_statement_revenue_and_eps_null",
            "all_valuation_metrics_null",
            "no_income_statement",
            # MOVED 2026-09-06 (goal: "get Missing SEC/XBRL to zero the right way" sweep):
            # finra_data_unavailable/finra_api_unreachable/missing_finra_data relocated to
            # "Ownership data unresolved" below - FINRA short-interest settlement data is a
            # wholly separate feed from SEC EDGAR/XBRL (load_short_interest_finra.py never
            # touches SEC filings at all), so bucketing it here inflated the "Missing SEC/XBRL
            # data" headline with rows that no XBRL fix could ever close, and undercounted
            # "Ownership data unresolved" (which already holds the same-shape 13F/insider
            # external-feed gaps). See "Ownership data unresolved"'s 2026-09-06 comment for
            # the new location. This mapping shift alone moves 345 rows off the SEC/XBRL
            # headline (live-counted via /api/scores/coverage same day) without touching any
            # underlying data.
            # ADDED 2026-08-20 (goal session: coverage-categorization audit): these three
            # (load_sec_valuations.py, load_value_quality_growth_metrics.py) mean the
            # filer's own SEC filing section is incomplete/inconsistent (not merely
            # unset) - "the SEC data we have for this statement can't be trusted", the
            # same class as the other "Missing SEC/XBRL data" reasons above, not an
            # unexplained "Other" error. See load_sec_valuations.py's 2026-08-20
            # data_unavailable-filter fix for why these rows are excluded rather than fed
            # into ratios (113 live symbols were computing pe_ratio=1000+ from them before
            # that fix).
            "incomplete_sec_filing_income",
            "incomplete_sec_filing_balance",
            "incomplete_sec_filing_cashflow",
            # ADDED 2026-09-02 (goal session: SEC/XBRL missing-data sweep, financial-
            # statements post_run() flag-sync fix): same "the SEC data we have can't be
            # trusted/converted" class as incomplete_sec_filing_* above.
            # 'fpi_currency_data_rejected' is the new reason loaders/load_financial_
            # statements.py's post_run() now writes when it force-nulls a foreign private
            # issuer's stale home-currency values (see _reject_stale_fpi_currency_data).
            # 'raw_unconverted_currency_stale_value_20260829' is migration 1250's one-off
            # cleanup of the same bug class for BAK/BSAC/EDN/GGAL/HEPS/SUPV/TEO/TGS/TKC/TV -
            # both were falling through to "Other (errors / excluded)" for lack of a mapping.
            "fpi_currency_data_rejected",
            "raw_unconverted_currency_stale_value_20260829",
            # ADDED 2026-09-06 (goal: "SEC/XBRL missing data to zero" sweep): same root fact
            # as fpi_currency_data_rejected/raw_unconverted_currency_stale_value_20260829
            # above (a foreign private issuer - GGAL/BBAR/BSAC/SUPV/TEO/TKC/TGS/TV and
            # siblings - tags its required statement concepts only under a hyperinflationary/
            # unsupported local currency, e.g. ARS, never USD or any MAJOR_CURRENCIES entry),
            # just written by transform()'s initial-fetch path (has_unsupported_currency_
            # only_fact, sec_statements_shared.py) instead of post_run()'s force-null path -
            # kept in the SAME category as its two siblings above for consistency, not moved
            # to "Legitimate / not applicable": this team's existing precedent treats
            # "genuinely knowable if a reliable FX rate ever becomes available" as still
            # "Missing SEC/XBRL data", not a permanent exemption.
            "unsupported_currency_no_fx_rate",
            # ADDED 2026-09-03 (same sweep, stranded-fix recovery): load_financial_statements.py's
            # _reject_stale_all_none_annual_row reason (Q1-mislabeled-as-annual force-null, e.g.
            # OFRM) - post_run()'s flag-sync previously hardcoded 'fpi_currency_data_rejected' for
            # every required-field force-null regardless of cause; now each rejection carries its
            # real reason (see that file's 2026-09-03 fix comment on _record_explicit_null_rejection).
            "no_usable_annual_duration_fact",
            # ADDED 2026-09-03 (same sweep, [[quarterly_duration_fact_comparative_fp_aliasing_
            # residual_10sym_20260903]] follow-up): a one-time direct correction of 8
            # quarterly_income_statement Q1 rows (AMTB/BGC/GPOR/KOP/PNR, symbol+fiscal_year
            # pairs) hand-verified to be whole-annual-fact duplicates from an old extraction
            # bug - live re-extraction confirms the CURRENT code no longer produces a Q1 fact
            # for these exact periods at all (not even an all-None row), so
            # _reject_stale_all_none_annual_row's guard can never reach them and a normal
            # backfill can never self-heal this population - a direct data correction was the
            # only path, same as 49b5569f8's original 293-symbol correction.
            "quarterly_row_orphaned_annual_duplicate",
            # ADDED 2026-09-02 (same sweep): load_value_quality_growth_metrics.py's row-level
            # early-return reason when the symbol's annual_balance_sheet row itself is
            # unavailable/empty (see that file's ~line 4528) - was also unmapped, falling
            # through to "Other (errors / excluded)" for all 44 affected symbols across
            # every quality_metrics column derived from the balance sheet.
            "no_recent_balance_sheet_data_reported",
            # ADDED 2026-09-02 (same sweep): load_value_quality_growth_metrics.py's sibling
            # reason for fcf_yield/fcf_margin/fcf_to_net_income/free_cash_flow when the
            # symbol has no free cash flow reported across recent fiscal years (real OCF/
            # capex gap, not a computation error) - same unmapped-fallthrough bug as
            # no_recent_balance_sheet_data_reported above.
            "no_recent_free_cash_flow_reported",
            # REMOVED 2026-09-06 (tie-out-checker follow-up; found while chasing an unrelated
            # test failure this same duplicate caused): "revenue_absent_from_anchor_year" used
            # to have its own entry here, but the 2026-09-06 "MOVED" fix below re-added it to
            # the "Legitimate / not applicable" bucket as one of six anchor-year-mismatch
            # sibling reasons - leaving BOTH entries in place made this bucket win first-match
            # (this list is checked in order), silently no-oping that move for this one key
            # while its five siblings moved correctly. See the "Legitimate / not applicable"
            # bucket's own 2026-09-06 comment for the full rationale.
            # ADDED 2026-09-02 (same sweep, static cross-check of every reason-string literal
            # in the SEC/XBRL loader files against this map - not just live DB counts, which
            # can't see a reason string that hasn't fired yet in the current data): 7 more
            # genuinely unmapped "the SEC data isn't there" facts found this way.
            # no_recent_operating_cash_flow_reported: sibling of no_recent_free_cash_flow_
            # reported above (both from load_value_quality_growth_metrics.py's OCF/FCF
            # windowed gates) - only the FCF one was ever added.
            "no_recent_operating_cash_flow_reported",
            # ADDED 2026-09-02 (static sweep continuation, quality_row_db anchor-year
            # investigation follow-up): total_cash/cash_per_share/ebitda_unavailable_reason's
            # own "sec_valuations has no row at all for this symbol" fact (see
            # load_value_quality_growth_metrics.py's ~line 6303/6316/6341, commits 1547b826c/
            # 37fc38252) - same "the SEC data we have can't be used" class as the other reasons
            # here. Never mapped despite landing 2026-09-02 08:20 CDT; caught by a full static
            # grep of every reason-string literal actually assigned in the loader's
            # `_unavailable_reason` ternary blocks vs this list, not live DB counts (which
            # currently show 0 live rows for this exact string - sec_valuations coverage may
            # have since improved for the originally-affected symbols - but the string is real,
            # reachable code, and must still resolve to a real category when it does fire).
            "no_sec_valuations_row",
            # ADDED 2026-09-02 (same sweep, restricted to load_sec_valuations.py):
            # invalid_shares_outstanding - _compute_valuations()'s final "no valid
            # shares_outstanding from any SEC/DEI-derived tier" fact (all upstream tiers
            # - reported_shares_outstanding, DEI dei:EntityCommonStockSharesOutstanding,
            # dual-class/FPI fallbacks, etc. - come up empty, ~line 2143). Reachable via the
            # main _compute_valuations() call site (line 1447), currently 0 live rows (data
            # happens to be clean right now) but a real unmapped string that would silently
            # fall to "Other" the moment it next fires. NOTE: its sibling "invalid_price"
            # (~line 2135, current_price <= 0) is deliberately NOT added here - that one is a
            # price_daily/prices-table gap, not a SEC/XBRL fact, so it correctly belongs in
            # "Other (errors / excluded)" below, same reasoning as stale_price_data there.
            "invalid_shares_outstanding",
            # entity_name_not_found/submissions_not_found_404/submissions_empty/
            # no_submissions: load_company_info_sec.py/load_earnings_calendar_sec.py/
            # load_current_reports_8k.py's own "SEC submissions.json has nothing for this
            # symbol/CIK" facts - same class as cik_not_found already above.
            "entity_name_not_found",
            "submissions_not_found_404",
            "submissions_empty",
            "no_submissions",
            # stockholders_equity_never_tagged_in_filings/total_liabilities_not_reported:
            # pb_ratio/debt_to_assets's own "never tagged this concept, full history" gates in
            # load_value_quality_growth_metrics.py - same class as stockholders_equity_not_
            # reported/total_debt_not_itemized already above.
            "stockholders_equity_never_tagged_in_filings",
            "total_liabilities_not_reported",
            # filings_key_missing/recent_filings_key_missing: load_earnings_calendar_sec.py's
            # sibling to submissions_not_found_404/submissions_empty above - SEC submissions
            # response came back but was missing the expected "filings" key structure.
            "filings_key_missing",
            "recent_filings_key_missing",
            # sec_form345_bulk_data_unavailable: load_insider_transaction_velocity.py's SEC
            # Form 3/4/5 bulk-data feed absence, same class as no_form345_filings_in_lookback_
            # window in "Ownership data unresolved" below but for the bulk-feed-itself-down
            # case rather than a per-symbol lookback gap.
            "sec_form345_bulk_data_unavailable",
            # ADDED 2026-09-02 (SEC/XBRL missing-data sweep): utils/external/sec_form345_
            # transaction_velocity_cached.py's CachedForm345Aggregator.get_velocity_metrics
            # writes this directly (bypassing load_insider_transaction_velocity.py's own
            # except-TimeoutError handler, which produces sec_form345_bulk_data_unavailable
            # above) when the caller's own wait_for_download blocks past timeout_seconds
            # (1080s) waiting on the shared background Form 3/4/5 bulk download - same "the
            # SEC bulk feed didn't come back in time" fact, just a different code path to the
            # same outcome. Still live-firing today (17 rows, most recent within the last
            # day), not stale debris - was falling through to "Other (errors / excluded)".
            "Form345_download_timeout",
            # ADDED 2026-09-08 (/goal score-sanity sweep): same
            # sec_form345_transaction_velocity_cached.py CachedForm345Aggregator.get_velocity_
            # metrics call site as Form345_download_timeout directly above, but the branch hit
            # while the shared background Form 3/4/5 bulk download is still actively in
            # progress (not yet timed out) - same "the SEC bulk feed isn't ready yet" fact,
            # just the in-flight case instead of the gave-up-waiting case. Was unmapped,
            # falling through to "Other (errors / excluded)".
            "Form345_download_in_progress",
            # filing_date_unavailable/segment_data_unavailable: load_sec_segment_info.py/
            # load_sec_segment_metrics.py's own "SEC segment XBRL data isn't there" facts,
            # same class as the other segment-data reasons already above. These two tables
            # are display-only/unscored (_UNSCORED_TABLES) but the coverage report still
            # categorizes their reasons, so they should read honestly too.
            "filing_date_unavailable",
            "segment_data_unavailable",
            # ADDED 2026-09-02 (same sweep): loaders/helpers/sec_base.py writes this when a
            # full unfiltered SEC refetch no longer reproduces a fiscal year the DB
            # currently marks available - that year's data is retracted/no longer backed by
            # any live SEC filing, the same "SEC data we have can't be trusted" class as
            # incomplete_sec_filing_* above. Was unmapped (73 live rows,
            # quarterly_income_statement.reason).
            "stale_fiscal_year_not_confirmed_by_full_sec_refetch",
            # ADDED 2026-08-20: earnings_calendar_sec's genuine "no SEC filings exist for
            # this symbol" case (the old false-positive version of this reason - foreign
            # private issuers filing 20-F/6-K instead of 10-K/10-Q - was already fixed
            # 2026-08-19 by widening _EARNINGS_BEARING_FORMS; what remains is real absence).
            "no_sec_filings_found",
            # ADDED 2026-08-29 (goal session: coverage-categorization sweep):
            # load_company_info_sec.py's shares_outstanding_unavailable_reason - the
            # symbol's CIK/annual-report lookup never turned up any SEC 10-K/10-K-equivalent
            # filing at all, so shares_outstanding was never extractable. Was unmapped
            # (150 live rows).
            "no_annual_report_filing",
            # ADDED 2026-08-29 (same sweep): load_company_info_sec.py's third
            # shares_outstanding_unavailable_reason bucket - a real annual filing exists but
            # shares_outstanding wasn't tagged in its XBRL AND the raw-filing-text fallback
            # extraction also came up empty. Was unmapped (48 live rows).
            "shares_outstanding_not_in_xbrl_or_filing_text",
            # ADDED 2026-08-22 (goal session: "Top Causes of Missing Data" Other-bucket
            # sweep): load_positioning_metrics.py's per-field marker for "no FINRA
            # short-interest row on file for this symbol at all" (as opposed to
            # short_interest_finra.reason's table-level "finra_data_unavailable"/
            # "finra_data_unavailable" fed row - same underlying fact, just written by a
            # different loader onto a different table/column). Was sitting in "Other
            # (errors / excluded)" even though it's the identical "the FINRA feed simply
            # doesn't cover this issue" absence as finra_data_unavailable two lines above,
            # not an error - 585 of 712 live "Other" rows (82%) were this single reason,
            # making the "how much is a genuine unexplained error" signal in that bucket
            # far noisier than the real number. MOVED 2026-09-06 to "Ownership data
            # unresolved" along with its two siblings - see that bucket's comment.
            # ADDED 2026-08-20: utils/external/sec_xbrl_segments.py - the SEC companyfacts
            # API structurally never returns per-segment revenue at all (a permanent API
            # limitation, not a per-filer gap); kept here rather than "Legitimate / not
            # applicable" because it's the same "the SEC data isn't there" class as the
            # other segment-data reasons already in this bucket
            # (no_segment_revenue_in_xbrl_xml etc.), just a different root cause.
            "companyfacts_api_never_exposes_per_segment_revenue",
            # ADDED 2026-08-20 (goal session: unmapped-reason sweep, cross-checked every live
            # *_unavailable_reason value in the schema against this map): dividend_data's
            # equivalent of no_us_gaap_facts/no_xbrl_filings - the companyfacts response has no
            # "facts" key at all - was silently falling through to "Other (errors / excluded)"
            # for 11 live rows because nothing in this map matched it.
            "no_companyfacts",
            # ADDED 2026-08-20 (goal session: missing-data root-cause audit): utils/external/
            # sec_xbrl_segments.py's extraction returns this when every tagged segment's revenue
            # is negative (ASC 280 elimination/reconciling lines, excluded by design - see that
            # function's own comment) or the reportable total is exactly 0 - the segment XBRL
            # facts exist but aren't usable, same "SEC data we have can't be trusted" class as
            # the other segment-data reasons already here. Was unmapped and falling through to
            # "Other (errors / excluded)" (19 live rows, sec_segment_info.reason).
            "zero_total_segment_revenue",
            # ADDED 2026-08-21 (goal session: "is missing data really missing" audit):
            # load_company_profile.py's company_profile.reason - "no_sic_code_available"
            # means company_info_sec never resolved a SIC code for this symbol at all;
            # "sic_code_unmapped" (base of the dynamic "sic_code_unmapped:XXXX" reason,
            # matched via `base in keys` in _categorize_reason) means SEC assigned a real
            # SIC code but it has no SIC_TO_GICS mapping/division fallback yet - both are
            # "the SEC classification data isn't there/usable" facts, same class as the
            # other Missing SEC/XBRL reasons. Were unmapped and falling through to "Other
            # (errors / excluded)" (146 live rows combined).
            "no_sic_code_available",
            "sic_code_unmapped",
            # ADDED 2026-08-21 (same session): orphaned reason string with zero remaining
            # code references (grepped repo-wide) - written directly to the DB by a
            # one-off remediation script during the 2026-08-19 currency-conversion fixes
            # (see MEMORY.md's cny_currency_conversion / dividend_loader entries) that
            # NULLed out revenue/net_income poisoned by the pre-fix wrong-currency bug for
            # ~15-30 FPI symbols per statement table (TV, TKC, KSPI, IBN, KT, and other
            # ARS/TRY/KZT/INR/KRW filers), pending a real re-fetch to repopulate them.
            # Downstream value_metrics/quality_metrics already handle this safely (verified
            # live: no garbage ratios, correct NULL propagation with their own sensible
            # reasons), so this is inert bookkeeping debris, not an active bug - but it
            # represents a real "SEC data not currently available" fact and was falling
            # through to "Other (errors / excluded)" (61 live rows) for lack of a mapping.
            "currency_conversion_bug_remediation_20260819",
            # ADDED 2026-09-02 (goal session: "keep the missing-data number going down" SEC/
            # XBRL sweep, cross-checking today's own earlier fixes in this same session
            # against this map): load_value_quality_growth_metrics.py wired these four
            # "never tagged in any recent filing" gates (net_income_not_reported,
            # no_recent_total_assets_reported, eps_never_tagged_in_filings,
            # capex_never_tagged_in_recent_filings - see roe/roa/net_margin/sustainable_
            # growth_rate/asset_turnover/pe_ratio/peg_ratio/fcf_yield's own reason blocks)
            # earlier today to split a real "SEC never tagged this concept for this filer"
            # fact out of the generic missing_sec_data bucket, the same class as
            # total_debt_not_itemized/interest_expense_not_itemized/stockholders_equity_
            # not_reported already above - but none of the four were ever added here, so
            # all 286 live rows using them fell straight through to "Other (errors /
            # excluded)" instead, undoing the whole point of giving them an honest label.
            "net_income_not_reported",
            "no_recent_total_assets_reported",
            "eps_never_tagged_in_filings",
            "capex_never_tagged_in_recent_filings",
            # ADDED 2026-09-03 (SEC/XBRL missing-data sweep): current_ratio/quick_ratio's own
            # new no-data gates - see load_value_quality_growth_metrics.py's
            # _get_no_recent_current_assets_symbols() docstring for the live evidence (33 of 64
            # universe rows). Same "never tagged this concept for this filer" class as the four
            # reasons just above.
            "no_recent_current_assets_reported",
            "no_recent_current_liabilities_reported",
            # ADDED 2026-09-03 (SEC/XBRL missing-data sweep, live static-outlier check):
            # total_cash/cash_per_share's own new no-data gate - see load_value_quality_growth_
            # metrics.py's _get_no_recent_cash_symbols() docstring for the live evidence (FDXF,
            # a real S&P 500-flagged filer with real total_assets but never-tagged cash).
            # Same "never tagged this concept for this filer" class as the entries just above -
            # added here in the SAME commit as the reason string itself so it never sits
            # unmapped in "Other (errors / excluded)" even briefly (the exact "wiring half-
            # landed" mistake the four entries above this one were fixing after the fact).
            "no_recent_cash_reported",
            # MOVED 2026-09-02 (SEC/XBRL missing-data sweep, live audit of the "Other" bucket):
            # "symbol_not_found" was sitting in "Other (errors / excluded)" as a bare set
            # literal with no explanation. Repo-wide grep of every write site (only two:
            # load_sec_segment_info.py's _handle_symbol_not_found and
            # load_current_reports_8k.py's CIK-lookup branch) shows both mean exactly
            # "self.sec_client.symbol_to_cik(symbol)"/"_get_cik(symbol)" found no SEC CIK for
            # this symbol - the identical fact "cik_not_found" already captures above, just a
            # different literal from two specific loaders. Not a processing error; a real SEC/
            # XBRL data gap. Was mislabeled as an unexplained "Other" error (53 live
            # sec_segment_info rows + 17 live current_reports_8k rows).
            "symbol_not_found",
        },
    ),
    (
        "Insufficient history",
        {
            "insufficient_history",
            "insufficient_quarterly_history",
            "insufficient_prior_year_data",
            "insufficient_quarterly_data",
            "insufficient_eps_data",
            "insufficient_eps_growth_datapoints",
            "insufficient_revenue_data",
            "insufficient_price_history",
            "insufficient_quarterly_eps_history",
            # ADDED 2026-08-20 (goal session: missing-data root-cause audit): loaders/
            # technical_indicators.py's compute_ad_rating() returns None (which
            # load_positioning_metrics.py then labels "ad_calculation_failed", despite the name
            # sounding like an error) only when len(close) < 20 or the recent window is all-NaN -
            # not a calculation bug, the same "not enough price history yet" fact as
            # "insufficient_price_history" right above (both come from
            # positioning_metrics.ad_rating_unavailable_reason). Was unmapped and falling through
            # to "Other (errors / excluded)" (11 live rows).
            "ad_calculation_failed",
            # ADDED 2026-08-21 (goal session: beta_unavailable_reason genericization fix,
            # loaders/load_risk_metrics_daily.py's _get_beta_from_db): the stock/benchmark
            # price series didn't have enough overlapping history yet to compute a
            # covariance-based beta - same "not enough history yet" class as
            # insufficient_price_history, just three different checkpoints along that
            # computation (SPY's own series, the aligned overlap, the resulting return
            # count) rather than one. See that function's docstring for the full set of
            # beta failure reasons - extreme_beta below is the one that ISN'T this class.
            "spy_price_data_insufficient",
            "insufficient_common_dates",
            "insufficient_returns",
            # ADDED 2026-09-03 (SEC/XBRL missing-data sweep, synchronous static sweep):
            # loaders/load_risk_metrics_daily.py's sibling beta-computation gate to the three
            # above - SPY's own aligned-window return variance came back exactly 0 (a
            # degenerate covariance denominator, distinct from extreme_beta below which fires
            # AFTER a beta value was successfully computed). Same "beta couldn't be computed
            # at all from this window" class as spy_price_data_insufficient/
            # insufficient_common_dates/insufficient_returns, not extreme_beta's "computed but
            # implausible" class. Was unmapped, falling through to "Other (errors / excluded)".
            "spy_variance_zero",
            # ADDED 2026-08-29 (goal session: coverage-categorization sweep, live audit of
            # the "Other (errors / excluded)" bucket via lambda/api/routes/scores.py's own
            # _get_scores_coverage output): load_value_quality_growth_metrics.py's
            # quality_score_unavailable_reason - available_quality_weight cleared 0 but
            # missed the min_quality_weight_pct completeness floor (thin-sample
            # extrapolation, not honest data) - same "not enough underlying data to trust a
            # computed value" class as the other reasons in this bucket, just phrased around
            # "completeness" instead of "history". Was unmapped (179 live rows).
            "insufficient_completeness",
            # ADDED 2026-09-02 (same sweep, static cross-check): earnings_growth_4q_avg/
            # eps_growth_stability/quarterly_growth_momentum's own "found fewer than 8
            # quarters of history with a same-quarter-prior-year match" case
            # (load_value_quality_growth_metrics.py) - same "not enough history yet" class as
            # insufficient_quarterly_history two lines above, just a more precise label for
            # the year-over-year-matching sub-case.
            "insufficient_year_over_year_quarterly_history",
            # ADDED 2026-09-04 (goal session: "fix all SEC/XBRL" sweep): load_stock_scores.py's
            # composite-score unavailability reasons for when the underlying pillar metrics
            # tables (quality_metrics/value_metrics/growth_metrics) have no usable rows at all
            # for a symbol - same "not enough history/data to trust a computed result" class as
            # the other reasons in this bucket. no_value_metrics_found/no_quality_metrics_found
            # (written to composite_score.reason when the source metric table has zero rows),
            # no_growth_inputs_available (when growth_metrics computation exhausted all available
            # years without finding enough history). no_growth_metrics_found/no_*_scores_computed
            # are similar composite-unavailability reasons from load_stock_scores.py when the
            # pillar computation completely failed. Were unmapped and falling through to "Other
            # (errors / excluded)".
            "no_value_metrics_found",
            "no_quality_metrics_found",
            "no_growth_metrics_found",
            "no_growth_inputs_available",
            "no_momentum_scores_computed",
            "no_value_scores_computed",
            # ADDED 2026-09-04 (same sweep): load_stock_scores.py/load_positioning_metrics.py's
            # risk/stability/momentum composite-score unavailability reasons - same "not enough
            # data to compute" class as no_value/quality/growth_metrics_found above. These are
            # sibling reasons generated when their respective input tables (stability_metrics/
            # positioning_metrics) have insufficient data or the computation failed due to
            # insufficient history (sparse/thin sample). Were unmapped.
            "no_stability_metrics_found",
            "no_momentum_data_available",
            "no_risk_scores_computed",
            "insufficient_risk_inputs_thin_sample",
            "insufficient_breadth_history_or_missing_ratios",
            "insufficient_growth_inputs_thin_sample",
        },
    ),
    (
        "No analyst coverage",
        {
            "no_analyst_coverage",
            "no_analyst_estimates",
            "analyst_estimates_not_in_sec_filings",
            # ADDED 2026-08-20: load_earnings_calendar.py's equivalent of "no coverage" -
            # same underlying fact (nobody publishes forward estimates/dates for this
            # symbol), just for the earnings-calendar table instead of analyst_* tables.
            "no_earnings_coverage",
            "no_next_earnings_available",
            # ADDED 2026-08-31 (goal session: reason-code accuracy sweep): distinct from
            # "no_analyst_estimates" - the symbol HAS real, current analyst coverage
            # (a real analyst_earnings_estimates row), just not this one specific derived
            # forward-growth/estimate-revision figure. See
            # ValueQualityGrowthMetricsLoader._get_analyst_forward_growth_estimates's own
            # docstring for the live evidence (AFRM/DB/VOD/NWG/WELL/L). Still fundamentally an
            # analyst-coverage gap, same bucket, more precise label.
            "analyst_coverage_incomplete_for_field",
        },
    ),
    ("Stale fiscal data", {"stale_fiscal_data"}),
    (
        "Ownership data unresolved",
        {
            # MOVED 2026-09-06 (goal: "get Missing SEC/XBRL to zero the right way" sweep,
            # relocated from "Missing SEC/XBRL data" above): FINRA short-interest settlement
            # data (load_short_interest_finra.py) is a wholly separate feed from SEC EDGAR/
            # XBRL - it was miscategorized as an "XBRL" gap even though no SEC filing fix
            # could ever close it. Same class of external-feed gap as the 13F/insider-
            # transaction reasons already in this bucket.
            "finra_data_unavailable",
            "finra_api_unreachable",
            "missing_finra_data",
            "no_resolved_13f_holdings",
            # ADDED 2026-09-02 (same sweep, static grep of load_institutional_holdings_13f.py):
            # fetch_incremental()'s own "no row (or a row with institutional_ownership_pct
            # still NULL) found in institutional_holdings_13f for this symbol" fallback marker
            # (~line 316/360) - same "no 13F coverage" fact as no_resolved_13f_holdings above,
            # just written from the per-symbol incremental lookup path instead of the bulk
            # fetch_global() batch writer. Currently 0 live rows (fetch_global appears to be
            # the path that actually runs in production) but real, reachable code.
            "not_found_in_institutional_holdings_13f",
            "institutional_data_not_available",
            "shares_outstanding_unavailable",
            "shares_outstanding_unavailable_for_pct_calc",
            "no_form345_filings_in_lookback_window",
            "no_insider_transactions_in_lookback",
            # ADDED 2026-09-03 (synchronous static sweep): load_insider_transaction_velocity.py's
            # fetch_incremental() - `reason = metrics.reason or "no_data"` - fires when the
            # velocity aggregator marks data_unavailable=True but supplies no specific reason
            # string. Same "no insider-transaction coverage for this symbol" fact as
            # no_insider_transactions_in_lookback directly above, just the generic fallback
            # case instead of the specific one. Currently 0 live rows but real, reachable code
            # on the same table/column as its sibling - was falling through to "Other (errors /
            # excluded)" for lack of a mapping.
            "no_data",
        },
    ),
    (
        "Implausible / rejected value",
        {
            "implausible_ratio",
            "shares_outstanding_invalid",
            # ADDED 2026-08-20: load_sec_valuations.py's market_cap sanity check (>10x vs
            # yfinance) rejects a mis-scaled shares_outstanding the same way
            # "shares_outstanding_invalid" does - this reason string existed in the loader
            # (and load_short_interest_finra.py excludes symbols carrying it, per its
            # 2026-08-20 fix) but was never wired in here, so every affected row fell
            # through to "Other (errors / excluded)" instead of this bucket.
            "shares_outstanding_scale_mismatch",
            # ADDED 2026-08-20 (goal session: unmapped-reason sweep): both confirmed via
            # loaders/load_value_quality_growth_metrics.py as genuine sanity-check rejections,
            # not errors - were silently falling through to "Other (errors / excluded)" for 15
            # live rows combined because nothing in this map matched them.
            # - implausible_dcf_result: the 2-stage FCFE DCF model produced a per-share value
            #   outside MAX_INTRINSIC_VALUE_PER_SHARE bounds (only reached when fcf_yield > 0 -
            #   the fcf_yield <= 0 case correctly returns negative_free_cash_flow instead, see
            #   intrinsic_value_reason_from_fcf_yield's own docstring/history).
            # - garbage_metric_value_implausible_growth_rate: an EPS/earnings growth rate whose
            #   magnitude exceeds MAX_PLAUSIBLE_GROWTH_PCT (2000%, tightened 2026-08-28 from the
            #   original MAX_TREND_PERCENTAGE_POINTS/100000% bound) - a near-zero denominator
            #   artifact, not a real growth rate, rejected the same way implausible_ratio is.
            #   RENAMED 2026-08-31 from "garbage_metric_value_abs_gt_100000" - that string had
            #   gone stale ever since the 2026-08-28 tightening (it still named the OLD 100000%
            #   bound while every site setting it had already switched to the 2000% one).
            "implausible_dcf_result",
            "garbage_metric_value_implausible_growth_rate",
            # ADDED 2026-09-02 (SEC/XBRL missing-data sweep): sibling of
            # garbage_metric_value_implausible_growth_rate above for non-growth-rate fields
            # (forward_eps_growth_current_fy and others, load_value_quality_growth_metrics.py)
            # - same implausible-value rejection, just missing from this set.
            "garbage_metric_value_implausible_ratio",
            # ADDED 2026-08-20 (goal session: missing-data root-cause audit): load_sec_valuations.py's
            # _sanity_check_pe_ratio (>10x vs yfinance) rejects a mis-scaled ttm_eps the same way
            # _sanity_check_market_cap rejects a mis-scaled shares_outstanding just above - same
            # per-filing XBRL scale-bug class, just a different concept. Was unmapped and falling
            # through to "Other (errors / excluded)" (35 live rows, sec_valuations.reason).
            "eps_scale_mismatch",
            # ADDED 2026-08-21 (goal session: beta_unavailable_reason genericization fix):
            # loaders/load_risk_metrics_daily.py's _get_beta_from_db rejects a computed
            # |beta| > 10 as a numerically degenerate regression result (near-zero SPY
            # variance denominator, not a real risk figure) - same class as implausible_ratio.
            "extreme_beta",
            # ADDED 2026-09-02 (same sweep, static cross-check): load_value_quality_growth_
            # metrics.py's forward_pe_reason - a real forward EPS estimate is on file, but the
            # resulting forward_pe fell below MIN_PLAUSIBLE_FORWARD_PE_RATIO (a near-zero-EPS
            # artifact, not a real valuation), rejected the same way implausible_ratio/
            # extreme_beta are rather than persisting a single extreme outlier value.
            "implausibly_low_forward_pe",
            # ADDED 2026-09-06 (goal: "SEC/XBRL missing data to zero" sweep, live-confirmed
            # CASH/TRN and 170 of 384 universe dcf_fcf_unavailable_reason='missing_cash_flow_data'
            # rows): sec_valuations_yield_dcf.py's ground-truth reason for when fcf_base was real
            # (proven by the symbol's own non-NULL fcf_yield, computed from that same fcf_base)
            # but the DCF-only net-borrowing near-cancellation guard nulled dcf_fcf_base anyway -
            # a deliberate "don't anchor a perpetuity on a distorted near-zero base" rejection,
            # the same "computed but rejected as implausible" class as implausible_dcf_result
            # above, not a genuine SEC/XBRL data gap. See that reason's own write-site comment.
            "dcf_fcf_nulled_by_net_borrowing_distortion",
            # ADDED 2026-09-07 (real-money-readiness /goal audit): loaders/helpers/vqg_value.py's
            # pe_ratio_reason cascade resolves to these two strings when sec_valuations_ratios.py's
            # _pe_earnings_too_volatile/_pe_earnings_tax_benefit_inflated guards deliberately null a
            # real, positive, anchor-year-EPS-backed pe_ratio as an earnings-quality distortion (a
            # loss-then-profit-year swing or a one-off tax-benefit-inflated net income) rather than
            # a genuine bargain. Same "computed but deliberately rejected" class as implausible_
            # ratio/implausible_dcf_result above - live-confirmed BA/RILY (too_volatile) and AES/
            # AXON/RIGL (tax_benefit_inflated), all real S&P/mid-cap names with complete SEC
            # financials, not data gaps. Was unmapped and would have fallen through to
            # "Other (errors / excluded)".
            "pe_earnings_too_volatile",
            "pe_earnings_tax_benefit_inflated",
        },
    ),
    (
        "Other (errors / excluded)",
        {
            "fetch_error:ValueError",
            "fetch_error:RuntimeError",
            "data_unavailable_during_load",
            "unable to fetch after retries",
            "no_historical_data",
            "fed_rate_fetcher_not_implemented",
            "no_data_returned",
            "no_price_data_after_validation",
            "historical_date_enrichment_only_for_latest",
            "missing_price_data",
            "excluded_by_naming_pattern",
            "no_recent_price",
            # ADDED 2026-09-08 (/goal score-sanity sweep): utils/loaders/exception_handler.py's
            # generic exception-classification handlers, called by handle_exception() from
            # load_sec_valuations.py, load_sec_segment_metrics.py, load_earnings_calendar_sec.py,
            # load_company_info_sec.py, and loaders/helpers/sec_base.py on real TimeoutError/
            # ConnectionError/HTTPError(429,503)/KeyError/ValueError/no-results outcomes - the
            # same operational-error class as fetch_error:ValueError/unable to fetch after
            # retries already in this bucket. Was unmapped, falling through to this bucket
            # anyway via the default but silently.
            "timeout_retryable",
            "connection_error",
            "rate_limit_or_service_unavailable",
            "api_schema_mismatch",
            "data_invalid",
            "no_data_found",
            # ADDED 2026-09-02 (SEC/XBRL missing-data sweep, live audit_unavailable_reasons.py
            # cross-check): loaders/load_risk_metrics_daily.py writes this literal (see the
            # STALE_PRICE FIX 2026-09-01 comment at its write site, ~line 411) onto
            # stability_metrics' beta/volatility/downside_volatility/max_drawdown_1y columns
            # when the symbol's price_daily feed has stopped updating (last close older than
            # STALE_PRICE_TRADING_DAYS_THRESHOLD) - deliberately not computing risk figures
            # from a frozen window. This isn't a SEC/XBRL gap (price_daily/yfinance is a
            # different data source entirely) and it isn't "missing" so much as "known-broken
            # for this symbol right now" - the same operational-error class as
            # no_recent_price/missing_price_data already in this bucket, just for a stopped
            # feed instead of an absent one. Was unmapped and falling through to the same
            # bucket anyway via the default, but silently (240 live rows, 30 symbols x 8
            # stability_metrics columns) - making it explicit here documents the fact instead
            # of leaving it looking like an unaccounted-for error.
            "stale_price_data",
            # ADDED 2026-09-02 (same sweep): load_sec_valuations.py's _compute_valuations()
            # current_price <= 0 gate (~line 2135) - sibling of no_recent_price/
            # missing_price_data already in this bucket. Deliberately NOT "Missing SEC/XBRL
            # data": current_price here is read from the prices table, a different data
            # source entirely, same reasoning as stale_price_data above. Currently 0 live
            # rows but reachable from the main _compute_valuations() call site.
            "invalid_price",
            # ADDED 2026-09-04 (goal session: "fix all SEC/XBRL" sweep): load_stock_scores.py/
            # load_risk_metrics_daily.py/load_yield_curve.py error/configuration reasons that
            # were unmapped. These are operational/transient error conditions (missing
            # configuration, external service issues, data processing failures) rather than
            # missing data gaps per se.
            # - yfinance not installed / No SPY option expirations available: yfinance
            #   configuration/availability issues (not a persistent data gap)
            # - unexpected_response_format / unknown error: malformed API responses or
            #   catch-all error conditions
            # - momentum_metrics_loader_failed: computational failure in momentum scoring
            # - yield_curve_fetcher_returned_unavailable_without_reason / yield_data_dict_empty_
            #   or_invalid: Fed rate fetcher / yield curve data processing issues
            "yfinance not installed",
            "No SPY option expirations available from yfinance",
            "unexpected_response_format",
            "unknown error",
            "momentum_metrics_loader_failed",
            "yield_curve_fetcher_returned_unavailable_without_reason",
            "yield_data_dict_empty_or_invalid",
            # ADDED 2026-09-04 (same sweep): load_stock_scores.py's capital_allocation/
            # exposure aggregation failure reasons for when the composite weighting couldn't
            # be computed from individual pillar scores (rare, all-or-nothing result).
            "exposure_no_result",
            # RESTORED 2026-09-07 (regression: landed in 97c7a2590, silently dropped by a bad
            # merge in 0cbce77c0 - real-money-readiness audit re-verified write-site still emits
            # this exact string). load_value_quality_growth_metrics.py's _get_positioning_data
            # writes this on a real DB/fetch exception, an operational error, not a data gap.
            "positioning_metrics_unavailable",
        },
    ),
    (
        "Legitimate / not applicable",
        {
            # ADDED 2026-09-11 (goal: "SEC/XBRL missing data under 300" push): a confirmed
            # FDIC/OCC/Fed-supervised bank that reports under Exchange Act Section 12(i)
            # instead of registering with the SEC - no SEC CIK exists, ever, for these (see
            # is_known_non_sec_filer_bank's module-level comment in
            # utils/external/sec_ticker_cache.py for the live FDIC BankFind + SEC
            # full-text-search verification trail). Distinct from generic "cik_not_found"
            # just below - that bucket still legitimately belongs in "Missing SEC/XBRL
            # data" since most of its population (renamed tickers SEC's bulk file hasn't
            # caught up with, etc. - see CIK_OVERRIDES) IS a fixable lookup gap.
            "fdic_designee_no_sec_cik",
            "non_dividend_paying_stock",
            # ADDED 2026-09-05 (SEC/XBRL missing-data sweep, dividend_yield TTM-fallback
            # follow-up): a real, confirmed dividend payment inside the 2-year non-payer
            # window but outside the 370-day TTM window - genuine recent data, just too
            # stale to compute a confident current yield from. Real fact, not an extraction
            # gap, same "Legitimate / not applicable" class as non_dividend_paying_stock.
            "dividend_lapsed_beyond_ttm_window",
            "unprofitable_stock",
            # ADDED 2026-09-02 (SEC/XBRL missing-data sweep, load_value_quality_growth_
            # metrics.py commits 7cfb8e7ae/e29d475a1): same "the ratio is mathematically
            # undefined for real business reasons, not a data gap" class as
            # unprofitable_stock two lines above. negative_enterprise_value = a genuine
            # net-cash-rich filer (total_cash alone exceeds market_cap + total_debt), so
            # EV/EBITDA and EV/Revenue have no meaningful denominator relationship;
            # zero_revenue_reported_this_period = a real $0.00 anchor-year revenue (e.g. a
            # wind-down period), so EV/Revenue and P/S are undefined for that period
            # regardless of other years' history. Both would otherwise fall through to
            # "Other (errors / excluded)" via _categorize_reason's default, undoing the
            # point of giving them an honest label in the first place.
            "negative_enterprise_value",
            "zero_revenue_reported_this_period",
            # ADDED 2026-09-03 (goal session: "get the missing-XBRL number down the right
            # way" sweep): no_revenue_reported was sitting in "Missing SEC/XBRL data" even
            # though _get_no_recent_revenue_symbols()/_get_never_tagged_revenue_symbols()'s
            # own docstrings already call it "structurally pre-revenue, not a loader gap"
            # (dominated by SPACs and pre-revenue clinical-stage biotech/pharma, live-
            # confirmed via company_profile.currency_code - all 322 sampled ebitda_margin
            # symbols are USD filers, not an FPI/currency-conversion population). Same
            # "mathematically undefined for real business reasons, not a data gap" class as
            # zero_revenue_reported_this_period one line above and unprofitable_stock two
            # lines below - the SEC filing IS complete, the company genuinely has no revenue
            # to divide by. Was inflating the headline by 1,339 rows (fcf_margin/
            # ebitda_margin/ev_revenue/ps_ratio/asset_turnover) for gaps that no re-fetch or
            # extraction fix could ever close, since there is no revenue fact to find.
            "no_revenue_reported",
            # ADDED 2026-09-06 (goal session: "SEC/XBRL missing data to zero" sweep):
            # interest_coverage's own reason from load_value_quality_growth_metrics.py's
            # vqg_quality.py for a symbol double-confirmed structurally debt-free (never
            # tagged ANY debt component AND never reports nonzero interest_expense) - operating
            # income / $0 interest expense is mathematically undefined, not missing data, same
            # "Legitimate / not applicable" class as no_revenue_reported/unprofitable_stock/
            # negative_enterprise_value just above.
            "no_debt_no_interest_expense",
            # ADDED 2026-08-29 (goal session: signal_quality_scores bare_reason_tables
            # addition): the backfill marker [[signal_quality_scores_historical_reason_backfill_20260829]]
            # applied to 53,567 pre-2026-08-29 rows that predate this table's reason-tracking
            # entirely - a known historical gap already closed, not an ongoing/actionable one.
            "historical_row_predates_reason_tracking",
            # ADDED 2026-08-22 (goal session: "No analyst coverage" bucket audit):
            # load_value_quality_growth_metrics.py's forward-looking analogue of
            # unprofitable_stock two lines above - a real analyst forward-EPS estimate is on
            # file, it's just negative (the company is projected to lose money next year), so
            # forward_pe is undefined the same way trailing pe_ratio is for a current loss.
            # Was sharing "no_analyst_estimates" with genuine zero-coverage symbols - see that
            # loader's own comment on forward_pe_reason for the live-confirmed scope (848 of
            # 1,560 rows, including real large-caps like MRNA/RBLX/RIVN/RKLB/WBD/BNTX).
            "negative_forward_eps",
            "reit_special_entity",
            # ADDED 2026-09-11 (goal: "SEC/XBRL missing data under 300" push):
            # sec_valuations_dcf_fcf_recategorize.py's _recategorize_royalty_streaming_dcf_fcf_
            # reason - a mining royalty/streaming company (GROY/MTA/OR/VMET/VOXR) has real,
            # growing operating cash flow but structurally never reports any PP&E-purchase
            # concept (it buys royalty/streaming interests, not mines) - same "Legitimate / not
            # applicable" class as reit_special_entity just above, distinct reason string since
            # these are real conventional IFRS filers, not a no-cash-flow-statement entity type.
            "royalty_streaming_no_capex",
            # ADDED 2026-09-05 (SEC/XBRL missing-data sweep, "implausible values" follow-up):
            # an ETF (stock_symbols.etf = 'true') files N-1A/N-CSR under the Investment
            # Company Act, not a 10-K, so it has zero annual_income_statement rows - the same
            # real business-model fact as reit_special_entity just above, not an extraction
            # gap. Live-confirmed SPY/QQQ/IWM (the universe's only active etf='true' symbols).
            "etf_no_sec_filings",
            # ADDED 2026-09-06 (goal: "SEC/XBRL missing data to zero" sweep, dividend_data
            # no_xbrl_filings investigation): load_dividend_data.py's own except FileNotFoundError
            # handler that WRITES this reason already calls it "permanent and legitimate (mutual
            # funds, shells), not a loader failure" in its own comment - it was just never moved
            # to match that comment's own conclusion. Live-sampled the full active-scored
            # population (496 rows, ~90 distinct symbols): dominated by closed-end funds/trusts
            # that file N-CSR/N-PORT, never a 10-K (Gabelli GAB/GDV/GUT/GLU/GNT, BlackRock
            # BCX/BDJ/BGR/BGY/BHK/BOE/BSTZ/BTX/BTZ, Franklin FT/PIM/PPT, Royce RGT/RMT/RVT, abrdn
            # HQH/HQL, DWS KTF, BNY LEO, Barings MCI/MPV, Central Securities CET), oil/gas/mineral
            # royalty trusts (SBR/CRT/SJT/PBT/MTR - no operating XBRL by design), ETFs (SPY/QQQ -
            # same etf_no_sec_filings class just above), OZK (see
            # bank_ozk_fdic_designee_no_10k_structural_genuine_20260903 in memory - FDIC Section
            # 12(i) designee, no SEC 10-K ever), and foreign banks filing 20-F/6-K with no XBRL
            # companyfacts at all (IBN/ICICI Bank - live-confirmed CIK 1103838's companyfacts
            # endpoint 404s). Every sampled case is a real, permanent, non-SEC-XBRL-reporting
            # entity, not an extraction gap - was inflating "Missing SEC/XBRL data" for a
            # population this pipeline can never close regardless of extraction-code quality.
            "no_xbrl_filings",
            # ADDED 2026-09-05 (SEC/XBRL missing-data sweep, "implausible values" follow-up):
            # a real, reported $0.00 total_assets/stockholders_equity (a blank-check/shell
            # company pre-merger, e.g. OBX) - a known business fact, not an extraction gap.
            # Distinct from "no_recent_balance_sheet_data_reported" just below (which stays in
            # "Missing SEC/XBRL data" - a genuine "never tagged" gap for most of its
            # population).
            "zero_total_assets_reported_shell_entity",
            # ADDED 2026-09-04 (goal: "under 6k the right way" sweep): load_value_quality_
            # growth_metrics.py's preferred_or_debt_security_no_common_equity_ratio -
            # AFGB/DTB/DUKB/BHFAL/KMPB/DCBG/MNSBP and siblings are preferred-stock/subordinated-
            # debenture tickers sharing their parent's CIK, so real common-equity EPS/book-value/
            # revenue-per-share data exists but doesn't belong to this instrument - a P/E, P/B,
            # or P/S computed from it would be wrong, not just missing. See that helper's own
            # docstring for the live evidence.
            "preferred_or_debt_security_no_common_equity_ratio",
            "negative_free_cash_flow",
            "negative_book_value",
            "negative_earnings_growth",
            # ADDED 2026-09-06 (goal: "SEC/XBRL missing data to zero" sweep): peg_ratio's own
            # reason function (vqg_shared.py's peg_ratio_reason_from_eps_history) now mirrors
            # _compute_peg_ratio()'s low-base-year rejection (a real, positive prior_year_eps
            # that's a one-off litigation/impairment trough relative to the filer's own EPS
            # history - same GILD/AA-shaped bug the value side already fixed, see
            # peg_ratio_low_base_effect in memory) - the data IS real, the ratio is just not
            # meaningful off that anchor year, same "not applicable" class as
            # negative_earnings_growth just above.
            "peg_ratio_low_base_effect",
            "negative_invested_capital",
            "growth_undefined_sign_change",
            # MOVED 2026-09-06 (goal: "SEC/XBRL missing data to zero" audit): the six
            # anchor-year-mismatch reasons below (revenue/eps/net_income/ocf/fcf/operating_income
            # _absent_from_anchor_year) were incorrectly grouped in "Missing SEC/XBRL data"
            # even though the data genuinely EXISTS in SEC filings - we deliberately DON'T
            # compute ratios from multi-year-stale data, not because the data is missing, but
            # because using stale revenue/EPS/cash-flow would produce misleading current-period
            # ratios. The data is "not applicable to use", not "missing". Live-verified impact:
            # 98 + 206 + 342 + 39 + others = 600+ symbols. Moving them drops "Missing
            # SEC/XBRL data" by ~600+ while correctly categorizing the actual business fact
            # (the anchor year's specific metric wasn't tagged, but an earlier year's was).
            "revenue_absent_from_anchor_year",
            "eps_absent_from_anchor_year",
            "net_income_absent_from_anchor_year",
            "operating_cash_flow_absent_from_anchor_year",
            "free_cash_flow_absent_from_anchor_year",
            "operating_income_absent_from_anchor_year",
            # ADDED 2026-08-29 (goal session: coverage-categorization sweep): _growth_reason()
            # in load_value_quality_growth_metrics.py's two siblings to
            # growth_undefined_sign_change directly above, from the exact same function - a
            # growth rate that's mathematically undefined (not merely unmeasured) because a
            # stock split/reverse-split changed the share count between the two comparison
            # points (growth_undefined_share_count_discontinuity, 2,044 live rows) or because
            # the prior-year base value was too close to zero for a percentage to be
            # meaningful (immaterial_prior_year_base, 1,275 live rows). Both were unmapped and
            # falling through to "Other (errors / excluded)" - together with the sign-change
            # case already here, these three cover every _growth_reason() branch.
            "growth_undefined_share_count_discontinuity",
            "immaterial_prior_year_base",
            # ADDED 2026-08-29 (same sweep): roce_pct's own negative-denominator undefined
            # case (load_value_quality_growth_metrics.py) - capital_employed <= 0, same
            # "the ratio is mathematically undefined for this company's balance sheet" class
            # as negative_invested_capital/negative_book_value directly above, just for ROCE
            # instead of ROIC/P-B. Was unmapped (183 live rows).
            "negative_capital_employed",
            # ADDED 2026-08-29 (same sweep): load_company_info_sec.py's shares_outstanding_
            # unavailable_reason for foreign private issuers - domestic shares_outstanding is
            # structurally inapplicable/excluded for FPIs by design, same permanent-exemption
            # class as foreign_private_issuer_shares_unavailable below (a different loader's
            # string for the same underlying FPI fact). Was unmapped (1,035 live rows - the
            # single largest unmapped reason found this sweep).
            "fpi_shares_excluded_domestic_only",
            # ADDED 2026-08-19 (goal session continuation): foreign private issuers are
            # exempt from mandatory 10-Q quarterly SEC reporting - a permanent regulatory
            # fact, not a data gap that more loader coverage could ever close. See
            # load_value_quality_growth_metrics.py's _compute_quarterly_metrics for the
            # live-confirmed CHKP/FVRR case this distinguishes from genuine
            # "insufficient_quarterly_history".
            "foreign_private_issuer_no_quarterly_filings",
            # ADDED 2026-08-19 (same session): foreign private issuers structurally never
            # file Form 8-K (they use 6-K instead) - same permanent-exemption distinction as
            # above, for current_reports_8k. See load_current_reports_8k.py.
            "foreign_private_issuer_no_8k_filings",
            # ADDED 2026-08-19 (same session, live-caught after backfilling): a PRE-EXISTING
            # reason string (load_insider_holdings_sec.py/load_insider_transaction_velocity.py,
            # predates this session) was never wired into this categorization at all - every
            # symbol using it fell through to "Other (errors / excluded)" instead of this
            # bucket. Live-confirmed: backfilling those two loaders' already-correct FPI
            # distinction relabeled 1,052 symbols to this reason, and "Other" visibly jumped
            # by exactly that amount on the live dashboard before this fix - the same
            # permanent-exemption fact as the two reasons above, just for Form 3/4/5 insider
            # filings (foreign private issuers are exempt from Section 16 reporting).
            "foreign_private_issuer_exempt",
            # ADDED 2026-08-20: same permanent-exemption class as the reasons above, for
            # short_interest_finra's short_pct computation - FPIs have no shares_outstanding
            # source that isn't in home-market (non-ADS) units, so short_pct is structurally
            # uncomputable, not a data gap. See load_short_interest_finra.py's max_fail_rate
            # comment (root-caused by load_sec_valuations.py's 2026-08-19 FPI unit-mismatch fix,
            # commit a123cdb46).
            "foreign_private_issuer_shares_unavailable",
            # ADDED 2026-08-19 (same session, industry-specific nuance pass): registered
            # investment companies (closed-end funds - the BlackRock BBN/BCAT/BGT/BIT/BKT-class
            # trusts and similar) file under SEC's "cef"/"ffd" XBRL taxonomies instead of
            # standard 10-K us-gaap/ifrs-full - live-confirmed those taxonomies contain zero
            # dividend/distribution concepts (N-2 prospectus fee-table data only), a permanent
            # structural absence, not a loader gap. See load_dividend_data.py's fetch_incremental.
            "registered_investment_company_no_xbrl",
            # ADDED 2026-09-06 (goal: "SEC/XBRL missing data to zero" sweep): closed-end funds/
            # investment trusts (the same Gabelli/Invesco/Franklin/Eaton Vance/Royce/Tri-
            # Continental-class population as registered_investment_company_no_xbrl above -
            # GDV/GGZ/HQH/HQL/IIM/BGY/VCV/VMO/VVR/VKQ and 30+ live-confirmed siblings) don't just
            # lack GAAP dividend/cash-flow concepts, they never file a 10-K/10-K-A/20-F/20-F-A at
            # all (only fund-specific forms - N-Q/NPORT-P/40-17G) - the same permanent structural
            # fact load_company_info_sec.py's has_annual_report_filing already exists to detect
            # (see its own docstring: "closed-end funds file neither"), but that loader's
            # shares_outstanding_unavailable_reason mislabeled it as the generic
            # "no_annual_report_filing" (Missing SEC/XBRL data) instead of this permanent-
            # exemption bucket. See load_company_info_sec.py's fetch_incremental for the
            # entity_type='other'/'investment' + sic_code IS NULL reclassification (same
            # discriminator _get_registered_investment_company_symbols() uses elsewhere, minus
            # its annual_balance_sheet-history requirement - these CEFs have zero rows there by
            # definition, since they never file the 10-K that table's loader parses).
            "registered_investment_company_no_annual_report",
            # ADDED 2026-09-05 (goal session: "SEC/XBRL missing data to zero" sweep): physical
            # commodity/currency/crypto trusts (GLD, SLV, IAU, GBTC, ETHE, the FXA-class
            # currency trusts, etc.) file a "Statement of Assets and Liabilities" with no GAAP
            # stockholders_equity concept - same permanent structural absence as the
            # registered-investment-company case above, for `etf_symbols`-registered tickers
            # rather than CEFs. See vqg_symbol_gates.py's
            # _get_etf_trust_no_stockholders_equity_symbols().
            "etf_trust_no_gaap_financials",
            # ADDED 2026-09-10 (missing-SEC/XBRL-under-300 push): AGG/IWM (iShares ETFs,
            # confirmed present in `etf_symbols`) were falling to load_current_reports_8k.py's
            # generic "symbol_not_found" (Missing SEC/XBRL data) because ETF share classes are
            # registered under their issuing Trust's own CIK/ticker and don't appear at all in
            # SEC's company_tickers.json or browse-edgar under the traded ETF ticker itself -
            # live-confirmed both symbols return zero CIK matches from either source. This is
            # not a resolvable "we can't find the CIK" gap (Missing SEC/XBRL data): ETFs are
            # investment companies that file N-1A/485BPOS under the Investment Company Act, not
            # Form 8-K under the Exchange Act at all - the same permanent structural exemption
            # as etf_trust_no_gaap_financials above, just for this loader. See
            # load_current_reports_8k.py's fetch_incremental for the etf_symbols check.
            "etf_no_8k_filings",
            # ADDED 2026-09-10 (same push): load_company_info_sec.py writes this when a
            # ticker's own security is a debt-like structured note or preferred share (e.g.
            # CCZ - "Comcast Holdings ZONES", a Zero-premium Exchangeable Note) rather than
            # common equity - there genuinely is no dei:EntityCommonStockSharesOutstanding
            # cover-page fact for a security that isn't common stock. Same permanent-
            # exemption class as vqg_symbol_gates.py's preferred/debt-security gate
            # ("preferred_or_debt_security_no_common_equity_ratio", handled elsewhere), just
            # for this loader's own reason string.
            "preferred_or_debt_security_no_shares_outstanding",
            # ADDED 2026-08-21 (goal session: missing-data root-cause audit, "Other" bucket
            # sweep): load_current_reports_8k.py writes this when a symbol's SEC submissions
            # feed genuinely contains zero 8-Ks (8-Ks are event-driven - executive changes,
            # M&A, material agreements - not periodic, so most quiet filers legitimately have
            # none in any given window; see that loader's own comment on this exact reason for
            # why it's distinguished from the FPI-exemption case, foreign_private_issuer_no_8k_filings,
            # already above). Not an error or a gap more loader coverage could close - was the
            # single largest contributor to "Other (errors / excluded)" (1,092 of 2,017 live
            # rows, >50%), silently making the "which loaders need fixing" report itself look
            # far noisier than the real gap.
            "no_8k_filings_in_recent_submissions",
            # RESTORED 2026-09-07 (regression: landed in 97c7a2590, silently dropped by a bad
            # merge in 0cbce77c0 - real-money-readiness audit re-verified both write-sites in
            # load_market_constituents.py still emit these exact strings). Both are permanent,
            # confirmed business facts: blank_check_shell_sic_6770_no_revenue fires only after
            # confirming SEC SIC 6770 + zero revenue ever; delisted_or_removed_from_exchange_feed
            # fires only after vanishing from the NASDAQ/otherlisted feed AND going stale in
            # price_daily (second orthogonal signal, added 2026-09-01 after a live EQR false
            # positive) - neither is a loader gap.
            "blank_check_shell_sic_6770_no_revenue",
            "delisted_or_removed_from_exchange_feed",
            # ADDED 2026-09-06 (goal session: "SEC/XBRL missing data to zero" sweep): symbol is
            # structurally unable to file traditional 10-K/10-Q filings due to entity type
            # (CEF/BDC/ETF/post-2024 banks), so it has no annual financial statements data -
            # same permanent-exemption class as registered_investment_company_no_annual_report and
            # etf_trust_no_gaap_financials above (the existing entity-type exemptions), just a
            # catch-all reason for any metric that hasn't yet wired per-entity-type checks.
            # Consolidated entity-type gate (_get_structural_entity_type_exemptions in
            # vqg_symbol_gates.py) enables this for all metrics uniformly.
            "entity_type_structurally_exempt_10k_filing",
        },
    ),
]
_COVERAGE_CATEGORY_ORDER = [name for name, _ in _COVERAGE_CATEGORY_RULES]
