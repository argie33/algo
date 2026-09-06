"""Factor/table scoring-scope classification plus reason-string categorization, for the
/api/scores/coverage report.

Split 2026-09-05 (file-size-ratchet compliance split of coverage.py): `_UNSCORED_TABLES`/
`_UNSCORED_FACTORS`/`_TABLE_GROUP` (which tables/factors can never move a live pillar score,
and which display group each table belongs to) and `_categorize_reason` (mapping any
`*_unavailable_reason` literal to its root-cause bucket, via `_COVERAGE_CATEGORY_RULES` in the
sibling coverage_category_rules.py) are grouped here as the report's "how do we classify this
row" logic - distinct from the rulebook data itself and from the source-tracking helpers in
coverage_sources.py, both of which this file's caller (_get_scores_coverage) also uses.
"""

from __future__ import annotations

from .coverage_category_rules import _COVERAGE_CATEGORY_RULES

# ADDED 2026-09-02 (goal session: "is this report classifying things right, especially
# valuation stuff"). This report's whole framing - the tab's own name, its tagline, the
# "Real Gap Instances" KPI - is "which SCORING factors are missing data". But a fair number
# of tracked *_unavailable_reason columns belong to fields loaders/load_stock_scores.py's
# live _score_value/_score_growth/_score_risk formulas do NOT read at all - they're kept
# computed/stored for the Deep Value page or historical/display purposes only (see each
# field's own "computed-but-unscored"/"REMOVED FROM SCORING" comment in that file). A
# 100%-missing ev_ebitda row was showing with the exact same visual weight as a
# 100%-missing pe_ratio row even though only pe_ratio can ever move stock_scores -
# live-confirmed via a fresh read of every current _score_* function body (not memory/
# docstrings, which the codebase's own fama_macbeth_composite_weights_stale_vs_live_pillar_
# formulas finding warns can drift from what's actually live). Deliberately keyed by
# (table, factor_name) rather than factor_name alone - a couple of these names could in
# principle collide with an unrelated, actually-scored field on a different table.
#
# Quality: _score_quality reads only the single pre-computed quality_score field, and that
# score's own upstream formula (load_value_quality_growth_metrics.py's quality_components,
# _score_quality's own 2026-08-26/27 docstring) is an 8-input weighted blend: roe(11%),
# roa(18%), roce_pct(18%, replaces roic_pct), debt_to_equity(18%, replaces debt_to_assets),
# fcf_margin(15%, replaces accruals_ratio), margin_volatility(~7%), asset_turnover(~7%),
# gross_profitability(~7%, replaces operating_profitability). The line below this comment
# block used to claim EVERY quality_metrics column was a genuine input "one stage earlier" -
# that was already disproven for 7 fields by the 2026-09-04 fix just below (interest_coverage/
# payout_ratio/operating_margin_trend/net_margin_trend/roe_trend/earnings_beat_rate/
# earnings_surprise_avg), and a full re-sweep the same day found the claim was wrong for 36
# MORE columns: only the 8 named above (plus quality_score itself) have any live
# quality_components entry - everything else in quality_metrics is fetched/computed/persisted
# for the Deep Value/StockDetail display pages only. See the second FIXED block below.
# Momentum has no entry either: none of its scored (momentum_3m, mom_12_1, rsi_14, macd,
# price_vs_sma_50/200) or unscored (momentum_6m) fields have their own tracked
# *_unavailable_reason column in this report at all (momentum_metrics only exposes a
# single bare `reason` column, and it isn't in `bare_reason_tables` below), so there's
# nothing to tag on that pillar.
#
# Positioning is handled as a whole TABLE, not a per-field set below (_UNSCORED_TABLES):
# _score_positioning was fully retired 2026-08-27 (Positioning pillar removed entirely -
# no method body remains in load_stock_scores.py, only a comment documenting the removal
# and the evidence trail) - every positioning_metrics/short_interest_finra field (A/D
# rating, institutional ownership, short interest and its % change) is display-only now
# (surfaced via the scores API's informational positioning_inputs field), not just a
# specific subset the way Value/Growth/Risk have a mix of scored and unscored fields.
#
# ADDED 2026-09-02 (goal session: SEC/XBRL missing-data sweep): sec_segment_info/
# sec_segment_metrics are ALSO a whole-table display-only case - grepped repo-wide across
# every scoring loader (load_value_quality_growth_metrics.py, load_enhanced_quality_
# growth_metrics.py, algo/scoring/, algo/orchestrator/phase7*) and found zero references;
# the only consumers are lambda/api/routes/market.py and financials.py (both informational
# display endpoints) plus this file's own coverage report. Segment revenue/count data has
# no path to any pillar score, same as Positioning - it just never got a whole-table entry
# here because the 317f7b60c/5c74a48e8 unscored-factor passes were scoped to fields that
# WERE recently scored and got retired, not tables that were never scored at all. These two
# tables alone account for 494 no_segment_dimension_contexts_in_xbrl_xml + 345
# no_segment_revenue_in_xbrl_xml (839 raw rows, scripts/audit_unavailable_reasons.py) that
# were inflating the "Missing SEC/XBRL data" headline for gaps that can never move a score.
_UNSCORED_TABLES: set[str] = {"positioning_metrics", "short_interest_finra", "sec_segment_info", "sec_segment_metrics"}

_UNSCORED_FACTORS: set[tuple[str, str]] = {
    # Value: _score_value's live formula is pe_ratio(27%) + pb_ratio(27%) + ps_ratio(27%)
    # + forward_pe(9%) + dividend_yield(10%) only - these six are computed/stored (Deep
    # Value page, PEG/margin-of-safety screens) but excluded from scoring entirely.
    ("value_metrics", "peg_ratio"),
    ("value_metrics", "ev_ebitda"),
    ("value_metrics", "ev_revenue"),
    ("value_metrics", "margin_of_safety"),
    ("value_metrics", "intrinsic_value"),
    ("value_metrics", "net_payout_yield"),
    ("value_metrics", "fcf_yield"),
    # market_cap: was the Size pillar's sole input, but _score_size/_score_positioning were
    # fully retired 2026-08-28/29 (no method body remains anywhere in load_stock_scores.py) -
    # market_cap itself stayed computed/stored (that file's own line ~3014 comment: "market_cap
    # is not scored anywhere"), just with nothing left to score it into.
    ("value_metrics", "market_cap"),
    # held_percent_institutions: zero references anywhere in load_stock_scores.py (verified via
    # repo-wide grep) - display-only (StockDetail.jsx / financials.py), never fed into any
    # pillar formula.
    ("value_metrics", "held_percent_institutions"),
    # Growth: _score_growth equal-weights the 12 GROWTH_SCORE_FIELDS; these 12 are computed
    # trend/YoY siblings explicitly removed from that field list (still shown on the scores
    # page as info rows per this repo's own "convert removed UI fields to info rows"
    # convention).
    ("growth_metrics", "book_value_growth"),
    ("growth_metrics", "net_income_growth_yoy"),
    ("growth_metrics", "operating_income_growth_yoy"),
    ("growth_metrics", "ocf_growth_yoy"),
    ("growth_metrics", "asset_growth_yoy"),
    ("growth_metrics", "fcf_growth_yoy"),
    ("growth_metrics", "eps_growth_stability"),
    ("growth_metrics", "eps_estimate_revision_90d_pct"),
    ("growth_metrics", "gross_margin_trend"),
    ("growth_metrics", "operating_margin_trend"),
    ("growth_metrics", "net_margin_trend"),
    ("growth_metrics", "roe_trend"),
    # earnings_beat_rate/earnings_surprise_avg: mislabeled proxies, confirmed dead code with
    # no scoring path/caller anywhere (memory: earnings_beat_rate/earnings_surprise_avg
    # mislabeled proxies finding). consecutive_positive_quarters: same - zero references in
    # load_stock_scores.py. All three were missed in this set's first pass (verified via
    # live API cross-check against GROWTH_SCORE_FIELDS, not assumed).
    ("growth_metrics", "earnings_beat_rate"),
    ("growth_metrics", "earnings_surprise_avg"),
    ("growth_metrics", "consecutive_positive_quarters"),
    # Risk: _score_risk uses volatility_60d/252d + beta + max_drawdown_1y + avg_dollar_volume_20d
    # only - the 30d volatility variant and all three downside-deviation variants are computed/
    # stored but never read by that function.
    ("stability_metrics", "volatility_30d"),
    ("stability_metrics", "downside_volatility_252d"),
    ("stability_metrics", "downside_volatility_60d"),
    ("stability_metrics", "downside_volatility_30d"),
    # FIXED 2026-09-04 (goal: SEC/XBRL "missing data" headline audit): quality_metrics'
    # own interest_coverage/payout_ratio/operating_margin_trend/net_margin_trend/roe_trend
    # were explicitly REMOVED from _score_quality's quality_components formula
    # (load_value_quality_growth_metrics.py, 2026-08-27 - see that formula's own docstring:
    # "Interest Coverage/Payout Ratio REMOVED 2026-08-27... neither ever approached
    # significance" and "Operating Margin Trend/Net Margin Trend/ROE Trend: relocated here
    # from Growth 2026-08-27, then REMOVED from scoring again the same day... Still
    # computed/persisted (quality_metrics table), not scored") - still computed/persisted/
    # displayed, but zero references anywhere in load_stock_scores.py's _score_quality
    # (verified via grep: each appears exactly once, only in the raw metrics-dict fetch,
    # never in the 8-input quality_components list). earnings_beat_rate/earnings_surprise_avg
    # (quality_metrics' OWN columns, distinct from the already-excluded growth_metrics
    # versions above) have zero references at all in load_stock_scores.py - same "mislabeled
    # proxies, confirmed dead code" finding as their growth_metrics siblings, just missed for
    # the quality_metrics table specifically. Combined, these 7 quality_metrics factors were
    # contributing 901 rows to the "Missing SEC/XBRL data" scored-only headline (6,345 ->
    # 5,444) for factors that were never part of the real scored surface at all - same "coverage
    # counted things outside the real scored universe" bug class as the CEF/BDC/ETN exclusion
    # fixes (`3629005d4`/`cbd8eb268`).
    ("quality_metrics", "interest_coverage"),
    ("quality_metrics", "payout_ratio"),
    ("quality_metrics", "operating_margin_trend"),
    ("quality_metrics", "net_margin_trend"),
    ("quality_metrics", "roe_trend"),
    ("quality_metrics", "earnings_beat_rate"),
    ("quality_metrics", "earnings_surprise_avg"),
    # FIXED 2026-09-04 (goal: SEC/XBRL headline audit, part 2 - full grep-verification sweep
    # of the remaining quality_metrics columns against _score_quality's live 8-input
    # quality_components formula, load_stock_scores.py + load_value_quality_growth_metrics.py).
    # Only roe/roa/roce_pct/debt_to_equity/fcf_margin/margin_volatility/asset_turnover/
    # gross_profitability (already excluded from this set - they're the real scored inputs)
    # and quality_score itself have any live path into a score. Every other quality_metrics
    # column is fetched/computed/persisted for the Deep Value/StockDetail display pages only -
    # confirmed one at a time, not assumed as a block:
    #  - roic_pct: superseded by roce_pct (quality_components' own comment: "ROCE replaces
    #    ROIC - fixes ROIC's cash-netting coverage gap").
    #  - debt_to_assets: superseded by debt_to_equity (correlated 0.67, debt_to_equity tests
    #    stronger per that formula's own docstring).
    #  - accruals_ratio: superseded by fcf_margin (independent signal, corr=0.13 - accruals_
    #    ratio itself never re-added after the fcf_margin swap).
    #  - operating_profitability: superseded by gross_profitability (Novy-Marx recovery under
    #    isolated FM testing, same docstring).
    #  - gross_margin/net_margin/operating_margin: "operating_margin_score/net_margin_score
    #    REMOVED 2026-08-26... no longer feed quality_score at all" (that removal's own inline
    #    comment) - gross_margin never had a _score variant to begin with (distinct from the
    #    scored gross_profitability, a different total-assets-denominator ratio).
    #  - gross_margin_trend: sibling of the already-excluded operating_margin_trend/
    #    net_margin_trend above, missed in the first (2026-09-04, part 1) pass.
    #  - quarterly_growth_momentum/earnings_growth_4q_avg/sustainable_growth_rate/
    #    revenue_growth_yoy/earnings_growth_yoy/net_income_growth_yoy/fcf_growth_yoy/
    #    ocf_growth_yoy/operating_income_growth_yoy/asset_growth_yoy: growth-shaped mirror
    #    columns quality_metrics also stores, but Growth's own _score_growth reads its
    #    OWN growth_metrics copies of these (GROWTH_SCORE_FIELDS) - the quality_metrics
    #    duplicates specifically have zero reader anywhere.
    #  - current_ratio/quick_ratio: "Current Ratio was tested and excluded (no cross-sectional
    #    signal despite being a standard quality-investing checklist item)" (_score_quality's
    #    own docstring) - quick_ratio never had a score variant either.
    #  - estimate_momentum_60d/estimate_momentum_90d/estimate_revision_direction/
    #    revision_activity_30d/revision_trend_score: per
    #    quality_metrics_estimate_revision_columns_deliberately_untouched (2026-08-28 memory) -
    #    "doesn't feed a scored pillar", computed only by the AWS-only enhanced-loader, no
    #    scoring consumer.
    #  - cash_per_share/ebitda/ebitda_margin/free_cash_flow/operating_cash_flow/total_cash/
    #    total_debt/fcf_to_net_income/ocf_to_net_income/eps_growth_stability/
    #    consecutive_positive_quarters: raw/reference figures with zero _score_quality
    #    consumption (repo-wide grep of load_stock_scores.py).
    # Verified via a live read of _score_quality/quality_components, not re-sampled from an
    # already-triaged bucket - same method as the part-1 fix directly above.
    ("quality_metrics", "accruals_ratio"),
    ("quality_metrics", "asset_growth_yoy"),
    ("quality_metrics", "cash_per_share"),
    ("quality_metrics", "consecutive_positive_quarters"),
    ("quality_metrics", "current_ratio"),
    ("quality_metrics", "debt_to_assets"),
    ("quality_metrics", "earnings_growth_4q_avg"),
    ("quality_metrics", "earnings_growth_yoy"),
    ("quality_metrics", "ebitda"),
    ("quality_metrics", "ebitda_margin"),
    ("quality_metrics", "eps_growth_stability"),
    ("quality_metrics", "estimate_momentum_60d"),
    ("quality_metrics", "estimate_momentum_90d"),
    ("quality_metrics", "estimate_revision_direction"),
    ("quality_metrics", "fcf_growth_yoy"),
    ("quality_metrics", "fcf_to_net_income"),
    ("quality_metrics", "free_cash_flow"),
    ("quality_metrics", "gross_margin"),
    ("quality_metrics", "gross_margin_trend"),
    ("quality_metrics", "net_income_growth_yoy"),
    ("quality_metrics", "net_margin"),
    ("quality_metrics", "ocf_growth_yoy"),
    ("quality_metrics", "ocf_to_net_income"),
    ("quality_metrics", "operating_cash_flow"),
    ("quality_metrics", "operating_income_growth_yoy"),
    ("quality_metrics", "operating_margin"),
    ("quality_metrics", "operating_profitability"),
    ("quality_metrics", "quarterly_growth_momentum"),
    ("quality_metrics", "quick_ratio"),
    ("quality_metrics", "revenue_growth_yoy"),
    ("quality_metrics", "revision_activity_30d"),
    ("quality_metrics", "revision_trend_score"),
    ("quality_metrics", "roic_pct"),
    ("quality_metrics", "sustainable_growth_rate"),
    ("quality_metrics", "total_cash"),
    ("quality_metrics", "total_debt"),
}

_TABLE_GROUP = {
    "quality_metrics": "Quality",
    "growth_metrics": "Growth",
    "value_metrics": "Value",
    "positioning_metrics": "Positioning",
    "stability_metrics": "Risk",
    "stock_scores": "Scoring",
    "stock_symbols": "Universe",
    "dividend_data": "Dividend",
    "analyst_sentiment_analysis": "Analyst",
    "analyst_upgrade_downgrade": "Analyst",
    "current_reports_8k": "Filings",
    "earnings_metrics": "Earnings",
    "insider_transaction_velocity": "Insider",
    "price_weekly": "Price",
    "yfinance_snapshot": "Snapshot",
    "market_health_daily": "Market",
    "institutional_holdings_13f": "Institutional",
    "analyst_earnings_estimates": "Analyst",
    "sec_segment_info": "Segments",
    "sec_segment_metrics": "Segments",
    "short_interest_finra": "Positioning",
    "sec_valuations": "Value",
}


def _categorize_reason(reason: str) -> str:
    base = reason.split(":")[0].strip()
    if reason.startswith("missing_critical_fields"):
        return "Missing SEC/XBRL data"
    if reason.startswith("yfinance returned no data"):
        return "Other (errors / excluded)"
    # ADDED 2026-08-29 (goal session: coverage-categorization sweep): growth_metrics's
    # whole-row reason when all 7 growth periods failed (load_value_quality_growth_metrics.py,
    # f"Insufficient historical data: {...fields...} could not be computed") - a full
    # sentence, not a snake_case code, so `base` (split on the first ":") comes out as
    # "Insufficient historical data" and never matches any set literal below. Live-confirmed
    # this exact sentence (2,240 rows, always the same 7-field list since it only fires when
    # every period fails) was the single largest contributor to "Other (errors / excluded)" -
    # same "not enough history" fact as the insufficient_history/insufficient_* reasons in
    # "Insufficient history" below, just phrased as a sentence instead of a code.
    if reason.startswith("Insufficient historical data:"):
        return "Insufficient history"
    # ADDED 2026-09-03 (SEC/XBRL missing-data sweep, static unmapped-reason sweep): sibling of
    # "Insufficient historical data:" above - load_value_quality_growth_metrics.py's PARTIAL
    # growth-period-failure branch (1-5 of 6 periods failed, data_unavailable stays False so
    # the real partial values aren't discarded) builds `growth_metrics.reason` as
    # f"Incomplete growth metrics: {failed_fields} failed to compute (insufficient history or
    # invalid data)" - same "not enough history yet" fact as the ALL-6-periods-failed sibling
    # just above, just phrased differently and for the partial case. Never matched any set
    # literal below (a full sentence, not a snake_case code), so 3,467 live rows were sitting
    # in "Other (errors / excluded)" - the second-largest contributor there after the already-
    # fixed sentence-shaped reasons - looking like unexplained errors instead of the same
    # ordinary "too few fiscal years on file yet" fact already correctly bucketed for every
    # other insufficient-history case.
    if reason.startswith("Incomplete growth metrics:"):
        return "Insufficient history"
    # ADDED 2026-09-02 (SEC/XBRL missing-data sweep): loaders/load_risk_metrics_daily.py
    # builds momentum_metrics.reason as a ";"-joined "momentum_{period}:insufficient_
    # price_history" list per missing period (e.g. "momentum_3m:insufficient_price_history;
    # momentum_6m:insufficient_price_history") - `base` (split on the first ":") comes out
    # as "momentum_3m", which never matches a set literal below. Same "not enough history"
    # fact as the other Insufficient history members, just phrased per-period.
    if "insufficient_price_history" in reason:
        return "Insufficient history"
    # ADDED 2026-09-06: same file's per-period sentence form ("Insufficient price history:
    # {n} days (need at least {m} for {period} momentum)") - same fact as the snake_case
    # sibling above, just phrased as a sentence. 39 active rows.
    if reason.startswith("Insufficient price history:"):
        return "Insufficient history"
    # ADDED 2026-09-06: load_positioning_metrics.py's whole-row reason when BOTH the FINRA
    # short-interest feed and the SEC 13F institutional-ownership feed came up empty
    # (f"short_interest:{source};institutional:{source}", sources are only ever "finra"/
    # "unavailable" and "sec_13f"/"unavailable" - this literal only fires when both read
    # "unavailable"). Same external-data-source-absent fact as missing_finra_data already in
    # "Missing SEC/XBRL data" below. 64 active rows (2-source and 3-source-with-insider forms).
    if reason.startswith("short_interest:") and "institutional:" in reason:
        return "Missing SEC/XBRL data"
    # ADDED 2026-09-06: load_risk_metrics_daily.py's per-period extreme-return rejection
    # (f"momentum_{period}:extreme_return_overflow(ret_pct={pct})") - same "computed but
    # rejected as implausible" fact as extreme_beta already mapped below, just per-period.
    if "extreme_return_overflow" in reason:
        return "Implausible / rejected value"
    # ADDED 2026-09-06: stability_metrics' whole-row `reason` is a ";"-joined "vol_30d:
    # insufficient_returns (N/30 required)" list - `base` comes out "vol_30d", unmatched, even
    # though the same sub-reason IS mapped alone in per-column *_unavailable_reason fields.
    # Live-confirmed 64 active rows stuck in "Other (errors / excluded)" for this alone.
    if "insufficient_returns" in reason:
        return "Insufficient history"
    # ADDED 2026-09-06: same file's beta-only branch prefixes the real beta_reason with
    # "beta: " (f"beta: {beta_reason}", e.g. "beta: extreme_beta: -10.67") - `base` comes out
    # "beta", unmatched, even though "extreme_beta"/"spy_price_data_insufficient" alone
    # already categorize correctly. Recurse on the part after "beta: " instead of duplicating
    # the whole ruleset. Live-confirmed 23 active rows stuck in "Other" for this alone.
    if reason.startswith("beta: "):
        return _categorize_reason(reason[len("beta: ") :])
    # ADDED 2026-08-20: loaders/helpers/sec_base.py builds this reason dynamically as
    # f"no_{period}_{statement_type}_data_in_sec_edgar_reit_or_special_entity" (6 period x
    # statement_type combinations) for REITs/SPAC-shells/other entities SEC EDGAR
    # structurally has no income-statement/balance-sheet/cash-flow data for - the same
    # permanent, non-fixable fact as the literal "reit_special_entity" reason already in
    # "Legitimate / not applicable" below, just per-statement-type instead of a single
    # flag. A set literal can't match every combination, hence the suffix check here.
    if reason.endswith("_data_in_sec_edgar_reit_or_special_entity"):
        return "Legitimate / not applicable"
    # ADDED 2026-08-29 (goal session: "full data" audit continuation, signal_quality_scores
    # bare_reason_tables addition above): loaders/signal_quality_scorer.py builds these two
    # reason strings dynamically with the symbol/date range embedded inline (f"... scoring
    # failed for {symbol} [{start} to {end}]: ..." / f"... No VCP patterns found for {symbol}
    # in date range {start} to {end}. ..."), so `base` is unique per symbol and never matches
    # a set literal. Both mean "the underlying event (a buy/sell breakout, a VCP
    # contraction pattern) genuinely hasn't occurred for this symbol in the lookback window
    # yet" - see [[buy_sell_daily_intermittent_71pct_shortfall_unresolved_20260821]] for the
    # live-confirmed evidence that buy_sell_daily is deliberately sparse/event-driven (most
    # of the universe legitimately has zero signals at any given time), not a loader bug -
    # same "not enough qualifying data yet" class as "Insufficient history"'s other members.
    if reason.startswith(("[SIGNAL_QUALITY]", "[VCP_NO_DATA]")):
        return "Insufficient history"
    # ADDED 2026-09-03 (SEC/XBRL missing-data sweep, synchronous static sweep): stock_scores'
    # own `reason` column - the FINAL composite-scoring stage, written by
    # load_stock_scores.py's `_build_score_row` when too few of the 5 pillars
    # (quality/growth/value/risk/momentum) were available to trust a composite score -
    # f"Completeness {pct:.2f}% < {threshold}% threshold (missing metrics: {...})". A full
    # sentence with a variable percentage, not a snake_case code, so `base` (split on the
    # first ":") comes out as "Completeness NN.NN% < NN.N% threshold (missing metrics" and
    # never matches a set literal below - same "sentence instead of a code" shape as
    # "Insufficient historical data:" above. Live-confirmed 227 rows, the largest unmapped
    # stock_scores reason. Same "not enough underlying data to trust a computed value" class
    # as insufficient_completeness (quality_score's own analogous gate, already in
    # "Insufficient history" below). Deliberately does NOT also catch the sibling
    # "Operation failed: {exception}" wrapper two lines below in the source (RuntimeError's
    # generic exception-message wrapper, `raise RuntimeError(f"Operation failed: {e}")`) -
    # that one can wrap an arbitrary exception, not always a data-completeness fact, so
    # bucketing it here would risk mislabeling a genuine bug as a data gap.
    if reason.startswith("Completeness "):
        return "Insufficient history"
    for cat, keys in _COVERAGE_CATEGORY_RULES:
        if base in keys or reason in keys:
            return cat
    return "Other (errors / excluded)"
