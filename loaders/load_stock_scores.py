#!/usr/bin/env python3
"""Stock Scores Loader - Multi-factor composite stock scoring.

Computes composite stock scores by aggregating:
- Quality metrics (ROE, margins, debt-to-equity ratio)
- Growth metrics (revenue growth, EPS growth)
- Value metrics (P/E, P/B, P/S ratios, dividend yield)
- Momentum/Relative Strength (1m/3m/6m/12m returns)
- Stability metrics (volatility, beta)

Positioning (A/D rating, institutional ownership, short interest) and Size (market cap) are
NOT part of the composite - both retired as top-level pillars (Positioning 2026-08-27, Size
2026-08-28, see BASE_PILLAR_WEIGHTS). Positioning's inputs are still computed/stored by
load_positioning_metrics.py and displayed via the scores API's positioning_inputs field,
informationally only. Size's input (market_cap) remains stored on value_metrics and surfaced
via the Value pillar's data - no synthesized size_score is computed anymore.

Each factor is normalized to 0-100 scale and weighted.
Final composite score is weighted average of all factors.

CRITICAL GOVERNANCE RULES:
- Minimum 1/6 metrics required for any stock score - degraded-mode scoring is allowed (SPACs/
  new listings, see Session 530 note on min_required_metrics below); trading gates separately
  filter on data_completeness >= 70% (min_completeness_score), which is the real entry-quality
  bar (no IPO exceptions there either)
- All stocks use uniform standards regardless of age or listing status
- Momentum requires proper lookback: 30d, 60d, 120d, 252d (no short-term fallback)
- All metric data validated before access (fail-fast on schema mismatches)
- Data corruption detected → RuntimeError (never silent degradation)
- Explicit data_unavailable markers in DB for operator visibility

Run: python3 loaders/load_stock_scores.py [--symbols AAPL,MSFT] [--parallelism 8]
"""

import sys

from loaders.loader_helper import setup_imports

setup_imports()

import itertools  # noqa: E402
import json  # noqa: E402
import logging  # noqa: E402
import math  # noqa: E402
from collections.abc import Iterable  # noqa: E402
from datetime import date, datetime, timezone  # noqa: E402
from typing import Any  # noqa: E402

import psycopg2  # noqa: E402
from psycopg2.extras import execute_values  # noqa: E402

from loaders.runner import run_loader  # noqa: E402
from utils.db.context import DatabaseContext  # noqa: E402
from utils.loaders.unavailable_markers import marker_loader_failed, marker_not_applicable  # noqa: E402
from utils.optimal_loader import OptimalLoader  # noqa: E402
from utils.type_conversion import safe_float  # noqa: E402

logger = logging.getLogger(__name__)

# Composite pillar weights (must sum to 1.0). Single source of truth - see
# _compute_stock_score's "Fixed base weights" block below for the full empirical-basis
# history/docstring. Module-level (not just a local var inside that method) specifically so
# tests and other consumers can import the real live value instead of hand-copying it - this
# codebase has repeatedly found stale hand-copied duplicates of these exact percentages
# drifting out of sync elsewhere (StockDetail.jsx's FACTOR_WEIGHTS, tests/test_formula_accuracy.py,
# algo/infrastructure/constants.py's REGIME_POSITION_SIZE_*, dashboard risk-panel display) -
# see [[risk_dashboard_position_size_multiplier_drift_fixed_20260825]] and siblings in memory.
# SIZE PILLAR RE-PROMOTED 2026-08-27 (user directive, reversing the 2026-08-26 removal - see
# _score_size's own docstring for the full history and the era-robust half-split evidence that
# prompted re-promotion: t=4.62 first half 2017-2021 / t=5.68 second half 2022-2026, its first
# actual robustness test rather than repeated point-estimates on a growing sample). Size gets
# 20%, the same top-level share as its original 2026-08-26 promotion; the other 5 pillars are
# scaled by x0.8 to free that weight, preserving their relative proportions to each other
# (quality 0.25->0.20, growth 0.18->0.14, value 0.21->0.17, risk 0.24->0.19, momentum
# 0.12->0.10 - rounded to whole cents, summing to exactly 0.80).
#
# POSITIONING RETIRED AS A COMPOSITE PILLAR 2026-08-27 (evidence-driven, see migration
# 1240_retire_positioning_score_from_stock_scores.sql for the full trail). Its only
# consistently-testable input, A/D rating (35% weight, previously kept on an explicit user
# directive despite null return-prediction evidence), was re-tested against the FULL
# available price history (2000-2026, 318 months, median 2,403 symbols - vs. the ~2015-on
# window every prior test defaulted to) specifically to rule out "not enough data" hiding a
# real signal: t=1.05, still not significant. institutional_ownership_pct and
# short_interest_pct/short_interest_pct_change have never had real historical depth in this
# database (institutional_holdings_13f: 1 row/symbol; short_interest_finra: ~2 real months of
# settlement-date coverage) - untestable, not merely untested. The pillar-level composite
# proxy is consistent with this: never significant in the top-level regression
# (algo/research/fama_macbeth_composite_weights.py), and its sign FLIPS between half-splits
# (t=+1.61 first half, t=-1.15 second half) - the signature of noise, not a real factor.
#
# Freed 12% moves to Growth (+6, 0.12->0.18) and Risk (+6, 0.18->0.24) - the two pillars that
# are consistently positive and never sign-flip across every specification of that same
# top-level regression (growth_proxy t=1.39 univariate/1.72 multivariate; risk_proxy
# [formerly stability_proxy] t=2.48 multivariate, the single strongest non-Size coefficient in
# the file, t=2.40/2.86 in both half-splits). Value and Momentum were left unchanged - both
# weak/inconsistent in this same regression, but with no stronger competing evidence to move
# them either direction (Value's own within-pillar FM work is separately robust; Momentum's
# composite-level coefficient is noisy but not worse than its neighbors, and moving it would
# just be encoding this run's specific noise). Quality's negative composite-level coefficient
# was deliberately NOT acted on - flagged in a prior pass as not half-split robust, a known
# collinearity artifact of this specific regression, not a finding about Quality itself (whose
# own within-pillar FM validation is separately strong).
#
# SIZE CUT 0.20->0.08, GROWTH/VALUE RAISED 20260828 (goal-mode data-coverage session). The
# 0.20 weight above was justified by algo/research/fama_macbeth_composite_weights.py's
# imputed-sample regression (missing pillar proxies 0-filled to grow the cross-section from
# ~1,100 to ~6,500 symbols/month) finding size_proxy t=7.38-7.39, "more than 3x every other
# pillar's own coefficient" per the 2026-08-27 promotion rationale above. That script was
# rebuilt this session to add a parallel STRICT COMPLETE-CASE regime (no imputation, real
# symbol-months only) specifically because missingness in quality/value/growth is not random -
# it concentrates in thin-SEC-filer micro-caps, the same population size_proxy (price x shares,
# essentially never missing) would be expected to correlate with. Result: size_proxy collapses
# to t=1.80-1.81 (not significant) in the complete-case regime - only growth_proxy (t=5.50
# imputed / 2.76-2.78 complete-case) and value_proxy (t=2.12-2.13 / 2.74) are significant AND
# same-signed in BOTH regimes, the bar this session established for treating a composite-level
# finding as real rather than an imputation artifact (see
# composite_weights_rebuilt_size_evidence_collapses_complete_case_20260827 /
# growth_score_saturation_bug_fixed_761_symbols_20260827 in memory for the full evidence and
# the coverage-bug-fixing work that preceded this decision). Quality/Risk (same-sign but not
# robust in both regimes) and Momentum (sign-flips, near-zero either way) were left unchanged -
# same "don't act without both regimes agreeing" discipline already applied to Quality's
# negative coefficient above, not a new standard invented for this pass. Freed 0.12 split evenly
# between growth (0.14->0.20) and value (0.17->0.23), proportional to their near-identical
# complete-case t-stats (2.76 vs 2.74) - not eliminating Size outright (some economic basis for
# a size premium remains in the literature even where this data doesn't robustly show it, same
# "modest weight for inconclusive evidence" treatment already given to Value's own fcf_yield/
# margin_of_safety), just no longer treating it as one of the two strongest pillars in the
# composite when the corrected methodology says it isn't.
#
# A/D rating, institutional ownership, and short interest are NOT deleted from the system:
# load_positioning_metrics.py keeps computing/storing them unchanged, and the scores API
# still surfaces them via positioning_inputs for display - only the synthesized 0-100
# "positioning_score" composite, which no longer has a coherent empirical basis, is dropped.
#
# SIZE RETIRED AS A COMPOSITE PILLAR 2026-08-28 (user directive: "just get rid of size",
# same evidence-driven retirement pattern as Positioning above, not a UX-only objection this
# time). Direct trigger:
# [[size_weight_collapse_reconfirmed_after_coverage_fixes_20260828]] - re-ran
# algo/research/fama_macbeth_composite_weights.py fresh after completing the data-coverage
# audit across all 6 pillars the user required before revisiting this (growth saturation bug,
# growth_metrics 66-symbol fix, dividend_yield fallback, momentum_metrics reason-tracking).
# Size's complete-case t-stat did NOT move (1.81 -> 1.80) - directly confirming the SIZE CUT
# comment's own MNAR hypothesis above: size_proxy (price x shares) is essentially never
# missing, quality/value/growth are frequently missing together for the same thin-SEC-filer
# population, so size_proxy's strong imputed-regime coefficient (t=7.38-7.39) was substantially
# proxying for "has real fundamentals data" rather than a clean size premium - fixing the
# specific coverage bugs did not change this, because the missingness is correlated across
# pillars for the same symbols, not caused by any single pillar's computation bug. Freed 0.08
# split evenly between growth (0.20->0.24) and value (0.23->0.27), the two pillars ROBUST
# (significant AND same-signed) in BOTH the imputed and complete-case regimes per that same
# re-run - identical redistribution logic to the SIZE CUT pass above, just finishing what that
# pass called "not eliminating Size outright" once the pending coverage-audit precondition
# was met and didn't change the answer. _score_size/_size_curve_score/update_size_percentiles
# removed entirely (composite is 5 pillars again: quality/growth/value/risk/momentum).
# market_cap itself is NOT deleted - value_metrics.market_cap keeps being computed/stored
# unchanged, just no longer synthesized into its own 0-100 size_score. Migration
# drops size_score from stock_scores/stock_scores_history (see migrations/ dir for the
# positioning-retirement migration this one is modeled on).
#
# RE-VERIFIED 2026-08-31, NO CHANGE (composite-score architecture research session).
# algo/research/fama_macbeth_composite_weights.py had drifted stale/BROKEN again by this date
# (still mapped a retired size_proxy -> BASE_PILLAR_WEIGHTS["size"], a KeyError against this
# dict's current 5 keys; growth_proxy/value_proxy/stability_proxy all several reweights out of
# date - see that script's own module docstring for the itemized list). Rebuilt from scratch
# against main's ACTUAL live formulas (110 months, 2017-06 to 2026-07): under this project's own
# "must be significant AND same-signed in both the imputed and strict-complete-case regime" bar,
# NO pillar clears it (growth/value: same-sign only, not both significant; quality/risk/momentum:
# DISAGREE outright between regimes). Risk's eye-catching imputed-regime t=5.49 fails hard in the
# complete-case check (t=-0.72, wrong sign) and is concentrated almost entirely in the second half
# (2022-2026) - the exact imputation-artifact pattern this dual-regime discipline exists to catch,
# not real evidence. Verdict: the weights below remain the best-supported choice by absence of a
# better one, not by fresh confirmation - a meaningfully different, more honest state than "proven
# correct." Separately re-confirmed pillar-based architecture over flat ML on the SAME corrected
# data: walk-forward OOS, live fixed-weight linear Spearman=0.0830 vs a raw-pillar tree model's
# 0.0160 (357,612 symbol-months, 2023-2026 test years) - same conclusion as the 2026-08-27
# raw-input-level test, now reconfirmed post-formula-drift rather than assumed still true.
#
# SAME SESSION, FOLLOW-UP (algo/research/composite_percentile_and_interaction_test_20260831.py):
# swept all 10 pillar-pair interactions (5 pillars, complete-case, same |t|>=2-both-eras bar) -
# only value_proxy x stability_proxy clears it (t_FULL=-3.90, both eras -2.74/-2.77), reconfirming
# the ALREADY-LIVE VALUE_RISK_INTERACTION_MAX_SHIFT mechanism below with corrected formulas, not
# just carrying it forward on old evidence. No other pair is a candidate for similar treatment.
# Also tested percentile-rank vs the current mixed fixed-curve/percentile scoring for scale
# consistency (Quality/Growth/Momentum/Risk use fixed curves, Value's PE/PB/PS use a real
# cross-sectional percentile via update_value_multiples_percentiles() - a genuine "are these
# comparable scales" question, not previously tested): an all-percentile composite variant edges
# the current approach on pooled walk-forward Spearman (0.0881 vs 0.0830) but is NOT era-robust by
# this file's own standard (wins clearly in 2023-24, roughly ties/trails in 2025-26) and loses
# decisively on Pearson (~0.02 vs ~0.05 both eras) - suggestive, not conclusive. Left as an open
# question for explicit user direction, not acted on unilaterally on a non-robust result.
#
# DECIDED 2026-08-31 (explicit user direction: "figure what is best and do what is best"):
# NOT switching to all-percentile pillar scaling. The Spearman edge fails this project's own
# |t|>=2-both-eras bar (ERA2 roughly ties/trails) and Pearson favors the current mixed fixed-curve/
# percentile approach (magnitude-preserving, unlike a pure order-only percentile rank - "z-score
# approach" in an earlier version of this note was loose/inaccurate phrasing for the same thing,
# not a reference to a literal z-score computation anywhere in this file's live formulas)
# decisively in BOTH eras - the same standard that rejected 9/10 pillar-pair interactions and 13/16
# per-metric curve candidates above applies here too; a non-era-robust pooled metric isn't grounds
# to override it just because this particular candidate is the "flagship" scale-consistency
# question. Per-metric curve-vs-percentile was already handled correctly at the right granularity
# (ROE/ROCE/size shipped where the win was real and consistent, see git history 2026-08-28) - this
# pillar-level, all-or-nothing version is a coarser question and loses on the evidence. Current
# mixed approach (Value's PE/PB/PS percentile-ranked, everything else fixed-curve-or-per-metric-
# percentile as already decided per-candidate) stays as-is. Don't re-raise this without a new era
# of data or a materially different test design - re-running the same 2023-2026 OOS window won't
# produce a different answer.
#
# SAME SESSION, SECOND FOLLOW-UP (algo/research/goal2_joint_raw_input_vs_pillar_composite.py,
# re-raised via /goal: "instead of factor pillar weights, the input relationship in whole").
# The pillar-summary-level re-verification above (6 proxies) doesn't answer whether skipping
# pillar aggregation ENTIRELY - one flat model over every raw input at once, no pillar
# boundaries - beats pillar-then-combine; a 2026-08-27 version of this exact test found yes,
# pillar-then-combine wins, but had drifted stale the same way the pillar-summary script had
# (missing asset_turnover/vol_252d entirely, stale Growth/Value/Risk weight dicts). Rebuilt
# against today's verified-in-code formulas (69 raw inputs incl. a real 60/252-trading-day Risk
# reconstruction and asset_turnover, 374,741 symbol-months 2016-01 to 2026-07, 207,209 OOS
# symbol-months across 5 independent test years 2022-2026): live pillar-then-combine Spearman
# 0.0709 vs. a joint tree's 0.0455 and joint ridge's 0.0155 (naive lasso worse still at every
# alpha tried) - same conclusion as 2026-08-27, now reconfirmed on corrected current formulas
# rather than carried forward stale. Absolute numbers moved (0.0910->0.0709 live_linear,
# 0.0357->0.0455 tree) since both the live formulas and this reconstruction's fidelity changed;
# the qualitative verdict didn't. vol_252d (new this rebuild) ranked #2 in tree feature
# importance behind macd_sign - a real signal, but the joint model still can't beat pillar
# aggregation's use of it. No production change from this result - it's further confirmation
# the existing architecture is not something to abandon for a flatter one, not new evidence for
# a different one.
BASE_PILLAR_WEIGHTS: dict[str, float] = {
    "quality": 0.20,
    "growth": 0.24,
    "value": 0.27,
    "risk": 0.19,
    "momentum": 0.10,
}

# GROWTH_SCORE_FIELDS: the multi-input equal-weighted blend _score_growth scores (RESTORED
# 2026-08-28, user directive - see _score_growth's docstring for the full history/evidence
# trail). Order matches GROWTH_SCHEMA in StockScoreAccordion.jsx - every field the frontend's
# Growth tab displays is scored here, not just whichever one field last "won" an isolated
# Fama-MacBeth test. Kept at module level (not a local inside _score_growth) so
# tests/unit/test_scores_frontend_weight_badges_match_backend.py can import it directly instead
# of re-deriving the field list via source-regex, same convention as BASE_PILLAR_WEIGHTS.
#
# ocf_growth_yoy/asset_growth_yoy REMOVED 2026-08-28 (user directive, /goal session: "remove
# these two from growth score and from react"). Raw values remain computed/persisted in
# growth_metrics (load_value_quality_growth_metrics.py) and available via the API for reference
# - only the scoring input and the frontend GROWTH_SCHEMA row were removed, same
# still-computed/no-longer-scored treatment this file already uses elsewhere (e.g. margin/ROE
# trend fields, altman_z_score).
#
# book_value_growth REMOVED 2026-08-28 (user directive, /goal session: live-observed
# persistent "No data" on StockDetail for the stock under review). Same still-computed/
# no-longer-scored treatment as above - raw value remains in growth_metrics (migration 1242)
# for reference, just no longer scored or shown in GROWTH_SCHEMA.
#
# operating_income_growth_yoy REMOVED 2026-08-28 (user directive, /goal session: "remove this
# Operating Income Growth (YoY) ... from growth from the score and the react"). Same still-
# computed/no-longer-scored treatment as above - raw value remains in growth_metrics
# (load_value_quality_growth_metrics.py) for reference, just no longer scored or shown in
# GROWTH_SCHEMA.
#
# 2026-08-31 INDUSTRY-ALIGNMENT REVIEW (goal session: "dig and be certain we come up with the
# right list... best regarded metrics for identifying the growth factor"). Compared the prior
# 11-field list against MSCI/Russell/S&P's own published Growth-factor methodologies and
# IBD CAN SLIM, then re-verified every quantitative claim directly against the live DB (not
# carried over from a prior memory - see feedback_verify_specific_quantitative_claims_before_trusting
# in memory for why that matters on this exact file). Two changes:
#
# 1. net_income_growth_yoy REMOVED. Every major growth-style methodology (MSCI, Russell, S&P,
#    Zacks, IBD) defines the "earnings growth" descriptor on a PER-SHARE (EPS) basis
#    specifically because it is buyback/dilution-adjusted - a company can grow raw net income
#    only by issuing shares (real dilution, no per-owner benefit) or shrink net income while
#    growing EPS via buybacks (common for mature compounders). Raw net-income growth is not a
#    named component of any of those methodologies. This is a methodological objection, NOT a
#    redundancy fix - live Spearman correlation vs eps_growth_1y is only 0.16 (re-verified
#    2026-08-31, matches the same-day correction in
#    growth_pillar_industry_alignment_reviewed_no_action_20260828 - net_income_growth_yoy is
#    NOT a near-duplicate of anything else in this blend), so it was carrying real independent
#    variance, just not the industry-standard variance for this factor.
# 2. forward_eps_growth_current_fy / forward_eps_growth_next_fy / forward_revenue_growth_next_fy
#    ADDED. Forward (analyst-consensus) EPS growth is the headline Growth descriptor in MSCI's
#    "Long Term Forward EPS Growth Rate", Russell's 2-year I/B/E/S forecast EPS growth, and
#    S&P's growth methodology - this pillar was previously 100% backward-looking with no
#    forward-estimate input at all (flagged as the clearest institutional-comparison gap in
#    growth_pillar_industry_alignment_reviewed_no_action_20260828, "not fixable now" at the
#    time). That's since changed: forward_eps_growth_current_fy/next_fy and
#    forward_revenue_growth_next_fy were added to growth_metrics 2026-08-29 (real yfinance
#    analyst-estimate data, not a placeholder) and now have live per-symbol coverage of
#    73.1%/75.8%/76.7% respectively - comparable to already-scored fields like fcf_growth_yoy
#    (72.1%) - even though analyst_earnings_estimates itself still only has ~24 distinct
#    snapshot dates (no backfill capability), too little historical depth to backtest
#    predictive power in this DB. Included on industry-standard-methodology grounds, consistent
#    with this pillar's standing user override to prioritize matching well-regarded growth
#    definitions over requiring a fresh era-robust regression result for every candidate (see
#    growth_pillar_restored_multi_input_not_inverted_user_override_20260828). Correlate weakly
#    with every backward-looking field already in this blend (|r|<=0.33, mostly <0.1) and with
#    each other (0.42 forward EPS vs forward revenue) - genuinely new information, not
#    redundant with anything already here. eps_estimate_revision_90d_pct (the 4th field on the
#    same table) deliberately NOT added - estimate-revision momentum is a distinct factor style
#    (Zacks Rank's basis) from a growth-RATE level, and mixing a revision-momentum metric into a
#    naive equal-weight average of growth levels would conflate two different things this file
#    is otherwise careful to keep separate (see Growth-vs-Momentum pillar separation elsewhere
#    in this file) - stays informational-only in GROWTH_SCHEMA, fetched but unscored, same
#    treatment as eps_growth_stability above.
#
# fcf_growth_yoy was also reviewed against this same "is it in MSCI/Russell/S&P's canon"
# standard and is the other non-canonical member (FCF growth isn't a named Growth-factor
# descriptor in any of the three) - kept anyway: it functions as a "quality of growth" check
# (cash-backed earnings growth vs an accounting-only number) rather than a duplicate growth-
# rate, is not correlated with anything else in the blend (|r|<=0.32), and this codebase
# already trusts cash-flow-based measures elsewhere (FCF Yield in Value). Secondary/
# supplementary rather than core-canon, but not "wrong" - left in.
#
# eps_growth_stability ADDED 2026-08-31 (/goal session, explicit user directive: "add earnings
# variability as additional input to growth score"). Previously fetched into `metrics` but
# deliberately excluded from GROWTH_SCORE_FIELDS/this blend (see the now-superseded note in
# _score_growth's docstring) because, unlike every other candidate here, it's a dispersion
# metric (population stddev, in percentage points, of the trailing-4-quarter YoY EPS growth
# rates - see _compute_quarterly_metrics in load_value_quality_growth_metrics.py), always >=0
# and "lower is better" rather than a signed growth rate on the same higher-is-better scale.
# "Earnings variability" is itself a named signal in institutional factor methodology (e.g. it's
# one of MSCI's own three Quality-index components, alongside ROE and leverage) - the user's
# framing of it as a Growth input rather than Quality is an explicit, direct product decision,
# not a methodology dispute to relitigate (same footing as this pillar's standing multi-input
# user override - see _score_growth's docstring). Real, live-computed data: 3,879/4,862 non-
# unavailable growth_metrics rows have a value (79.8% coverage, live-verified 2026-08-31 -
# comparable to already-scored fcf_growth_yoy's 72.1% and quarterly_growth_momentum's 79.5%),
# not a placeholder. Scored via a dedicated inverted piecewise curve
# (_score_growth's _score_eps_growth_stability), NOT _score_single_growth - see that helper's
# own docstring for why (this field's scale/shape has nothing in common with a signed growth
# rate, so it can't reuse the shared cap=30 linear transform every other candidate does).
# fcf_growth_yoy / eps_growth_stability REMOVED 2026-08-31 (goal session: "figure out what is
# right and best, best proven validated best practices" - user explicitly asked to judge every
# field on finance merit alone, not on what a prior session had already decided). Both were kept
# through 3 earlier reviews on "real, uncorrelated signal" grounds - true, but insufficient once
# actually held to the SAME two-part bar the other 12 fields already clear:
# 1. fcf_growth_yoy: not a named component of MSCI/Russell/S&P/IBD's Growth methodology (cash-
#    flow growth isn't a canonical Growth descriptor anywhere), AND its own era-split predictive
#    evidence - independently reproduced this session via
#    `python -m algo.research.fama_macbeth_growth_factors` (not reused from a prior claim) -
#    actively FLIPS SIGN with real significance both ways (H1 2014-2020-06 t=-2.09, H2
#    2020-06-2026 t=+2.45, full-sample t=0.43). This is the identical "era-inconsistent, reject"
#    pattern this file has used to reject every other flipping candidate (e.g.
#    net_income_growth_yoy/operating_income_growth_yoy, asset_growth_yoy under the no-flip
#    convention) - not weak evidence, actively unstable evidence.
# 2. eps_growth_stability: real, non-redundant signal (~0 correlation with every growth-rate
#    field, live-checked) and legitimate, well-established methodology - but it's MSCI's own
#    Quality-index earnings-variability component, not a Growth-factor descriptor in MSCI's,
#    Russell's, S&P's, or IBD's published methodology. Held to the same "must be a named
#    component of a real Growth methodology" standard as the other 12, it doesn't qualify for
#    THIS pillar - it may belong in Quality instead (which has no earnings-variability input of
#    its own, only the related-but-distinct Margin Volatility), but that's a separate Quality-
#    pillar decision, not made here. Still computed/persisted in growth_metrics and displayed as
#    a tracked-not-scored row in GROWTH_SCHEMA (frontend), per this repo's standing "convert
#    removed fields to informational rows, don't delete" practice - not scored here.
# Net result: 12 fields, all independently verified canonical to a named MSCI/Russell/S&P/IBD
# Growth-factor component, equal-weighted (1/12 ~= 8.3% each - see GROWTH_SCHEMA/weight badges).
GROWTH_SCORE_FIELDS: tuple[str, ...] = (
    "revenue_growth_1y",
    "eps_growth_1y",
    "revenue_growth_3y",
    "eps_growth_3y",
    "revenue_growth_5y",
    "eps_growth_5y",
    "forward_eps_growth_current_fy",
    "forward_eps_growth_next_fy",
    "forward_revenue_growth_next_fy",
    "sustainable_growth_rate",
    "quarterly_growth_momentum",
    "earnings_growth_4q_avg",
)

# GROWTH_INPUT_IMPLAUSIBLE_PCT (added 2026-08-31, /goal session - "make sure the results make
# sense" investigation). _score_single_growth's cap=30 already bounds every signed-rate
# candidate's OUTPUT at 100, but does nothing to distinguish a genuinely excellent ~30-100%
# grower from a candidate whose raw rate is in the hundreds or thousands of percent - both map
# to an identical, fully-saturated 100. Live-verified two such cases dominating the top of
# composite_score: KARO's eps_growth_1y=1889.36% traces to FY2026 net_income of $993.9M vs
# $50.8M the prior year on an almost-unchanged share count (30.89M -> 30.89M, no split) -
# implying a ~2x P/E on its $2.08B market cap, which is not a real recurring-earnings story,
# almost certainly a one-off item (asset sale/tax benefit/settlement) counted at face value.
# DX similarly has fcf_growth_yoy=739.5%, quarterly_growth_momentum=140.35% - both 5-25x this
# cap. Neither looks like corrupted data (both are internally consistent with their own
# financials, so the existing garbage-value bound elsewhere in this codebase - which catches
# actual data-corruption cases up to +/-2000% - correctly leaves them alone), but they are not
# comparable "growth quality" to a clean, sustainable 30-100% grower either. Standard factor-
# investing practice (MSCI Barra, AQR) winsorizes/excludes outlier raw inputs before scoring for
# exactly this reason - a single anomalous field shouldn't get to fully saturate a multi-input
# equal-weighted blend. Set well above any plausible genuine "excellent" grower (the cap=30
# curve already reaches its 100 ceiling at 30%) so normal strong growers (e.g. YB's real
# eps_growth_1y=123.18%) are unaffected - only truly extreme values are excluded from the blend
# entirely (same "drop what's missing, don't hand its weight to a different candidate" pattern
# _score_growth already uses for None values), rather than counted as a full-credit 100.
# Deliberately NOT applied to eps_growth_stability - its own inverted curve already penalizes
# large values toward 0, so no separate exclusion is needed there.
GROWTH_INPUT_IMPLAUSIBLE_PCT = 150.0

# GROWTH_MIN_FIELDS_AVAILABLE (added 2026-08-31, same /goal session, found while actually looking
# at post-reload live results rather than just trusting the code change). _score_growth's equal-
# weighted blend had NO minimum-coverage floor at all - `if component_scores:` accepted even a
# single available field and renormalized it up to a full 0-100 score. Live-verified this produces
# a real, visible problem: after the 12-field trim, symbols like ATTO/GFUZ/VRXA/KWM/BLSM (each with
# exactly 1 of 12 fields available, that one field happening to be >=30%) landed a saturated 100
# growth_score - indistinguishable in the DB from NVDA's real 100 (built from 11/12 fields, all
# genuinely strong). Live sweep of the full universe: 76/4882 non-null-growth_metrics symbols have
# <=2/12 fields available, 11 of those score >=90 - a small slice of the universe, but exactly the
# kind of thin-sample extrapolation that lands at the TOP of any growth-sorted view, disproportionately
# visible. This is the identical problem Quality already solved for itself - see _score_quality's
# docstring ("40-point minimum-available-weight floor out of a 101-point nominal total... below
# that, quality_score is None rather than a thin-sample extrapolation") - Growth just never got the
# same treatment when it moved from single-input to multi-input. 5/12 (~42%) mirrors Quality's
# ~40%-of-101 ratio; below this, _score_growth returns a data_unavailable marker instead of a
# score built from too little evidence, same "honest partial data, not thin-sample extrapolation"
# principle, not a new one invented here.
GROWTH_MIN_FIELDS_AVAILABLE = 5

# RISK_MIN_WEIGHT_AVAILABLE (added 2026-08-31, same /goal session - "dig in one more time" pass
# after fixing the identical problem in Growth). _score_risk had the same missing-floor gap:
# `if total_weight > 0: return weighted_sum / total_weight` accepted even a single available
# component. Live-verified before fixing (not assumed from the code alone): APMC/FTRA/CAES/CCCT/
# IPVV/MTNE and others each have ONLY max_drawdown_1y available (15% weight, the smallest of the
# 4 Risk components - volatility_60d 45%/volatility_252d 20%/beta 20%/max_drawdown_1y 15%), and
# each lands a risk_score of 97-99+ (near-perfect "safety") purely from that one field, with
# volatility and beta - 85% of the pillar's real signal - completely absent. Checked APMC's real
# price history directly (price_daily table) before assuming a bug: it genuinely is a flat-priced,
# ~$9.9-10.0 SPAC-trust-style instrument with only 42 days on file, so its tiny max_drawdown_1y
# value is REAL, not a scale-mismatch artifact - the bug isn't the drawdown number itself, it's
# that one thin, low-weight field alone is enough to produce a near-max composite risk_score.
# Universe-wide sweep confirmed this is live, not theoretical: 75/5101 scored symbols have <40%
# of Risk's weight available, 17 of those score >=90. Same fix pattern as Growth
# (GROWTH_MIN_FIELDS_AVAILABLE) and the same ~40% ratio as Quality's own established floor - 0.40
# here since Risk's weights are fractional (sum to 1.0), not Growth's field-count-based floor,
# since Risk is weighted (45/20/20/15) rather than equal-weighted.
# Deliberately NOT applied to Value or Momentum: live-swept both the same way (61 and 58
# thin-coverage symbols respectively) and found ZERO symbols scoring >=90 off <40% weight in
# either - Value's cross-sectional percentile-rank correction and Momentum's "skip weak
# momentum" None-handling already prevent the single-field-saturation failure mode structurally,
# so adding an artificial floor there would only cost real coverage without fixing anything real.
RISK_MIN_WEIGHT_AVAILABLE = 0.40

# VALUE x RISK INTERACTION (added 2026-08-28, goal: cross-pillar interaction sweep - see
# value_stability_interaction_found_robust_20260828 in memory). Swept all 15 pillar-proxy pairs
# via algo/research/cross_pillar_interaction_sweep_20260828.py (complete-case regime, current
# live formulas) - value_proxy x stability_proxy(risk) was the ONE pair to clear this repo's
# era-robustness bar (t=-4.09 full / -2.17 / -3.61, both halves same sign; every other of the 15
# pairs failed at least one half). Double-sort confirms cleanly: mean monthly fwd_ret spread
# between cheap and expensive stocks is +1.64pp among the riskiest tercile (0.216% vs 1.851%) and
# essentially FLAT (-0.02 to -0.05pp) among mid/safe terciles - Value's entire predictive edge in
# this sample is concentrated in higher-risk names, consistent with the standard rational-pricing
# explanation for the value premium (cheapness partly compensates for real distress risk).
# Implemented as a linear transfer between Value's and Risk's own weights, conditioned on that
# SYMBOL's own risk_score (0-100, higher=safer): more weight to Value when risk_score is low
# (risky), less when high (safe), with Risk's weight moving the opposite direction by the same
# amount - so quality+growth+value+risk+momentum always sums to the same 1.00 total
# regardless of any symbol's risk_score, and a stock with risk_score=50 (the midpoint) gets
# exactly the base 23%/19% split. Magnitude (VALUE_RISK_INTERACTION_MAX_SHIFT) is a deliberately
# moderate half of Value's base weight, not fit to the exact regression coefficient - this repo's
# standing practice (see e.g. Growth/Quality curve caps) is to implement a real, evidenced
# direction conservatively rather than the literal point estimate, which risks overfitting a
# single sweep. Only applied when risk_score is itself a real (non-marker) score - a symbol
# missing Risk data gets the unmodified base weights, same "skip what's unavailable" principle as
# everywhere else in this file.
VALUE_RISK_INTERACTION_MAX_SHIFT = BASE_PILLAR_WEIGHTS["value"] * 0.5


def _value_risk_adjusted_weights(risk_score: float | None) -> dict[str, float]:
    """Return BASE_PILLAR_WEIGHTS with Value's and Risk's weights adjusted for the
    value_proxy x stability_proxy interaction (see VALUE_RISK_INTERACTION_MAX_SHIFT docstring
    above). Falls back to unmodified base weights when risk_score isn't a real float (Risk
    pillar unavailable for this symbol) - no interaction without a real risk_score to condition on.
    """
    if risk_score is None:
        return BASE_PILLAR_WEIGHTS
    # risk_score in [0, 100], higher = safer. Center at 50 so a risk_score of exactly 50 (neither
    # notably risky nor safe) reproduces the unmodified base weights exactly.
    risk_centered = max(-1.0, min(1.0, (50.0 - risk_score) / 50.0))  # +1 at risk_score=0 (riskiest)
    shift = VALUE_RISK_INTERACTION_MAX_SHIFT * risk_centered
    weights = dict(BASE_PILLAR_WEIGHTS)
    weights["value"] = BASE_PILLAR_WEIGHTS["value"] + shift
    weights["risk"] = BASE_PILLAR_WEIGHTS["risk"] - shift
    return weights


class StockScoresLoader(OptimalLoader):
    table_name = "stock_scores"
    primary_key = ("symbol",)
    watermark_field: str = "updated_at"
    exclude_etfs_from_symbols = True  # Metric loaders (quality, growth, value, risk) exclude ETFs

    def run(self, symbols: Iterable[str], parallelism: int = 1, backfill_days: int | None = None) -> dict[str, Any]:
        """Override run to validate upstream metrics are ready before computing scores.

        CRITICAL: Pre-flight validation ensures all upstream metric loaders have sufficient
        coverage before attempting stock score computation. This prevents silent degradation
        from incomplete metric data (e.g., 50% availability = biased scoring that impacts trading).
        """
        self.validate_upstream_metrics_ready()
        return super().run(symbols, parallelism=parallelism, backfill_days=backfill_days)

    def validate_upstream_metrics_ready(self) -> None:
        """Check that upstream metric tables have sufficient coverage.

        Raises RuntimeError if critical metric loaders haven't populated data yet.
        Prevents silent score computation failure when metrics are missing due to loader timeouts.

        Two tiers:
        - required: value/risk - must have real coverage thresholds met
        - optional_sec: quality/growth - depend on SEC annual financials; may be all-unavailable
          if the annual_income_statement upstream is empty. Fail only if table is completely empty
          (loader never ran). All-unavailable is acceptable; per-symbol scoring handles gracefully.

        positioning_metrics REMOVED 2026-08-27: no longer a stock_scores upstream dependency
        now that Positioning is retired as a composite pillar (see BASE_PILLAR_WEIGHTS). The
        table itself is unaffected and still validated by its own loader - this loader just no
        longer reads it.
        """
        from utils.db.error_handlers import handle_db_errors

        with handle_db_errors("validate_upstream_metrics"):
            with DatabaseContext("read") as cur:
                # CRITICAL FIX 2026-07-05: growth_metrics is no longer optional.
                # Stock scores require minimum 3/6 metrics per GOVERNANCE.md for valid trading signals.
                # If growth_metrics is incomplete, stocks will score with insufficient factors, biasing
                # toward value/momentum and away from growth signals. This is dangerous for growth-focused
                # portfolios. Enforce minimum coverage threshold.
                required_metric_tables = {
                    "value_metrics": 0.15,  # ADJUSTED: Realistic min - S&P 500 dividend payers ~4,700 stocks (2.7% of ~175k)
                    "growth_metrics": 0.10,  # ADJUSTED: Realistic min - SEC-filing dependent (many small-caps have no annual filings)
                    "stability_metrics": 0.15,  # ADJUSTED: Realistic min - Beta calculation requires sufficient price history
                }
                # SEC-filing-dependent metrics: acceptable to have 0% real data if upstream
                # annual_income_statement is empty (known infrastructure gap). Only fail if
                # the loader never ran at all (0 rows in table).
                optional_sec_metric_tables = {
                    "quality_metrics",
                }

                for table_name, min_coverage in required_metric_tables.items():
                    # Check if data_unavailable column exists (migration 102 may not have been applied yet)
                    # RACE CONDITION FIX: Use single query to get both counts atomically
                    # This prevents stale row counts when concurrent pipelines are inserting
                    try:
                        # Get both available and total counts in one query for consistency
                        # COUNT FILTER is atomic and prevents row count changes between queries
                        cur.execute(f"""
                            SELECT
                                COUNT(*) FILTER (WHERE data_unavailable = false OR data_unavailable IS NULL) as available_count,
                                COUNT(*) as total_count
                            FROM {table_name}
                            """)
                    except psycopg2.ProgrammingError as e:
                        # CRITICAL: Schema mismatch is a fail-fast failure (GOVERNANCE compliance)
                        # Cannot proceed with scoring when data_unavailable column is missing
                        raise RuntimeError(
                            f"[STOCK_SCORES] CRITICAL: {table_name} missing data_unavailable column. "
                            f"Database schema is out of sync with application code. "
                            f"Migration for {table_name} has not been applied. "
                            f"ACTION: Apply pending database migrations before running stock scores loader. "
                            f"Cannot proceed with potentially incomplete/corrupt metric data."
                        ) from e

                    row = cur.fetchone()
                    available_count = row[0] if row else 0
                    total_count = row[1] if row else 0

                    if total_count == 0:
                        raise RuntimeError(
                            f"[STOCK_SCORES] Pre-flight validation failed: {table_name} is EMPTY. "
                            f"ROOT CAUSE: Upstream metric loader may not have run yet. "
                            f"ACTION: Check {table_name} loader step function execution logs. "
                            f"Cannot compute stock scores without metric data."
                        )

                    # Coverage = stocks with real data / all stocks that ran through loader
                    coverage = available_count / total_count if total_count > 0 else 0

                    if coverage < min_coverage:
                        # CRITICAL: Require strict minimum coverage - no grace windows
                        # Silent degradation from incomplete metrics masks data quality issues.
                        # If metrics aren't available, that's a problem that needs operator attention,
                        # not a condition to degrade gracefully around.
                        cur.execute(
                            f"SELECT symbol, COUNT(*) FROM {table_name} WHERE data_unavailable = true GROUP BY symbol LIMIT 5"
                        )
                        unavail_sample = cur.fetchall()
                        unavail_sample_str = ", ".join([s[0] for s in unavail_sample]) if unavail_sample else "(none)"

                        raise RuntimeError(
                            f"[STOCK_SCORES] Pre-flight validation failed: {table_name} coverage insufficient. "
                            f"Only {coverage:.1%} coverage ({available_count}/{total_count} stocks with real data). "
                            f"Required: {min_coverage:.0%} minimum (NO GRACE WINDOW). "
                            f"Sample unavailable symbols: {unavail_sample_str}. "
                            f"ACTION: Check upstream {table_name} loader for timeouts/failures or incomplete data. "
                            f"Typical causes: SEC API limits (quality/growth), yfinance throttling (value), price history gaps (stability). "
                            f"Do NOT attempt to score stocks without full metric coverage - incomplete metrics produce biased rankings."
                        )

                    # CRITICAL FIX Session 345: Check data freshness, not just availability
                    # Coverage check passes even if data is 30+ days old (historical filings from slow SEC APIs)
                    # Add staleness check to prevent stale metrics from poisoning score rankings
                    try:
                        cur.execute(f"""
                            SELECT MAX(updated_at) FROM {table_name}
                            WHERE data_unavailable = false OR data_unavailable IS NULL
                        """)
                        max_update_row = cur.fetchone()
                        if max_update_row and max_update_row[0]:
                            max_update_ts = max_update_row[0]
                            from datetime import datetime, timezone

                            now_utc = datetime.now(timezone.utc)
                            if max_update_ts.tzinfo is None:
                                # {table_name}.updated_at is a `timestamp without time zone`
                                # column written via SQL CURRENT_TIMESTAMP, so a naive value
                                # here is in the DB session's local wall-clock timezone
                                # (utils/bulk_insert_manager.py's documented convention), not
                                # UTC. Same bug class already fixed in
                                # algo/trading/pretrade_checks.py's re-entry cooldown and
                                # algo/risk/market_exposure.py's cache-age check: resolve the
                                # real session timezone dynamically instead of assuming UTC.
                                from utils.db.timezone_utils import get_db_timezone

                                naive_tz = get_db_timezone()
                                max_update_ts = max_update_ts.replace(tzinfo=naive_tz)
                            stale_days = (now_utc - max_update_ts).days
                            max_staleness_days = 14  # Metrics older than 2 weeks are stale
                            if stale_days > max_staleness_days:
                                logger.warning(
                                    f"[STOCK_SCORES] {table_name}: Data is {stale_days} days old "
                                    f"(max_update_ts={max_update_ts}). "
                                    f"Exceeds staleness threshold of {max_staleness_days} days. "
                                    f"Scores computed from outdated metrics may misrank stocks."
                                )
                    except Exception as staleness_check_err:
                        # Non-fatal: log but don't halt if staleness check fails
                        logger.warning(
                            f"[STOCK_SCORES] Could not validate {table_name} staleness: {staleness_check_err}"
                        )

                for table_name in optional_sec_metric_tables:
                    # RACE CONDITION FIX: Use single query to get both counts atomically
                    try:
                        cur.execute(f"""
                            SELECT
                                COUNT(*) FILTER (WHERE data_unavailable = false OR data_unavailable IS NULL) as available_count,
                                COUNT(*) as total_count
                            FROM {table_name}
                            """)
                    except psycopg2.ProgrammingError as e:
                        # CRITICAL: Schema mismatch is a fail-fast failure (GOVERNANCE compliance)
                        # Cannot proceed with scoring when data_unavailable column is missing
                        raise RuntimeError(
                            f"[STOCK_SCORES] CRITICAL: {table_name} missing data_unavailable column. "
                            f"Database schema is out of sync with application code. "
                            f"Migration for {table_name} has not been applied. "
                            f"ACTION: Apply pending database migrations before running stock scores loader. "
                            f"Cannot proceed with potentially incomplete/corrupt metric data."
                        ) from e

                    row = cur.fetchone()
                    available_count = row[0] if row else 0
                    total_count = row[1] if row else 0

                    if total_count == 0:
                        raise RuntimeError(
                            f"[STOCK_SCORES] Pre-flight validation failed: {table_name} is empty. "
                            f"Upstream metric loader may not have run yet. "
                            f"Cannot compute stock scores without metric data."
                        )

                    coverage = available_count / total_count if total_count > 0 else 0

                    # CRITICAL FIX 2026-07-05: Allow 0% coverage for optional_sec metrics if the loader ran
                    # (table has rows). This handles legitimate cases where all data is unavailable:
                    # - Small-caps/IPOs with no SEC filings (growth/quality metrics unavailable but loader ran)
                    # - This is NOT a loader failure; it's successful completion with all-unavailable data
                    # The check above (total_count == 0) catches the real error: loader never ran
                    if coverage == 0:
                        logger.warning(
                            f"[STOCK_SCORES] {table_name}: 0% real data coverage ({available_count} real / {total_count} total). "
                            f"All records marked data_unavailable (likely no {table_name} available for traded symbols). "
                            f"This is acceptable for optional SEC metrics; stock_scores will compute with fewer factors."
                        )

                logger.info(
                    "[STOCK_SCORES] Pre-flight validation passed: upstream metric loaders ready. "
                    "Proceeding with stock score computation."
                )

    def _prepare_batch_context(self) -> None:
        """Load all metric tables once instead of per-symbol (N+1 fix).

        Previously each of quality/growth/value/positioning/stability_metrics was queried with
        a separate `WHERE symbol = %s` per symbol (~5 x symbol_count round-trips per run), and
        the momentum query re-evaluated `(SELECT MAX(date) FROM price_daily)` as an inline
        subquery up to 4 times per symbol against an 8.6M+ row table. Now: bulk queries total,
        cached by symbol; momentum is read from momentum_metrics table (precomputed).
        positioning_metrics dropped from this batch-preload 2026-08-27 (Positioning retired as
        a composite pillar - see BASE_PILLAR_WEIGHTS).

        Per-symbol row layout in each cache dict matches the original per-symbol SELECT exactly
        (same column order, `data_unavailable` last), so _get_*_metrics indexing is unchanged.

        CRITICAL FIX 2026-07-18: Now reads momentum_metrics from database instead of computing
        from price_daily. momentum_metrics is populated by load_risk_metrics_daily.py and has
        momentum_1m/3m/6m/12m already calculated. This fixes the issue where stock_scores had
        all NULL momentum values despite momentum_metrics being populated.
        """
        self._batch_context = {}
        # Load configurable completeness threshold
        self._min_completeness_threshold = None
        try:
            with DatabaseContext("read") as config_cur:
                config_cur.execute("SELECT value FROM algo_config WHERE key = 'min_completeness_score'")
                config_row = config_cur.fetchone()
                if config_row and config_row[0]:
                    self._min_completeness_threshold = float(config_row[0])
                    logger.debug(
                        f"[STOCK_SCORES] Using configurable completeness threshold: {self._min_completeness_threshold}%"
                    )
        except Exception as config_err:
            logger.critical(
                f"[STOCK_SCORES FAIL-FAST] Could not load min_completeness_score from config table: {config_err}. "
                f"This is a critical data quality gate. Database may be inaccessible or corrupted. "
                f"Cannot proceed without explicit completeness validation configuration."
            )
            raise RuntimeError(
                f"[STOCK_SCORES CRITICAL] Failed to load min_completeness_score configuration: {config_err}. "
                f"This parameter is critical for data integrity validation. Check database connectivity and schema."
            ) from config_err

        # Use explicit default only if key truly doesn't exist (legitimate first-time setup)
        if self._min_completeness_threshold is None:
            self._min_completeness_threshold = 70.0
            logger.warning(
                "[STOCK_SCORES] min_completeness_score not configured in database. "
                "Using conservative default 70% - consider setting explicit value in algo_config table."
            )

        with DatabaseContext("read") as cur:
            cur.execute(
                "SELECT symbol, roe, roa, operating_margin, net_margin, debt_to_equity, "
                "current_ratio, quick_ratio, debt_to_assets, quality_score, data_unavailable, "
                "gross_margin, ebitda_margin, roic_pct, fcf_to_net_income, ocf_to_net_income, "
                "payout_ratio, free_cash_flow, operating_cash_flow, total_debt, total_cash, "
                "cash_per_share, ebitda, earnings_growth_yoy, revenue_growth_yoy, interest_coverage FROM quality_metrics"
            )
            self._quality_cache: dict[str, tuple[Any, ...]] = {row[0]: tuple(row[1:]) for row in cur.fetchall()}

            # net_income_growth_yoy/operating_income_growth_yoy/sustainable_growth_rate/
            # fcf_growth_yoy/ocf_growth_yoy added: computed by load_value_quality_growth_metrics.py
            # (mirrored from quality_metrics into growth_metrics as of 2026-08-03) but never
            # read here before - fetched and stored, zero influence on growth_score.
            #
            # gross_margin_trend/operating_margin_trend/net_margin_trend/roe_trend/asset_growth_yoy
            # added 2026-08-03: the mirroring step above was never actually exercised against a
            # working DB (local dev schema had stockholders_equity/cash_and_equivalents renamed
            # out from under it, crashing every fetch_incremental() call before it could compute
            # these fields at all) - once the schema was fixed, live-verified these 5 populate
            # with real, differentiated values (not NULL), disproving the prior "structurally
            # always NULL" premise.
            # eps_growth_stability added 2026-08-25: computed by
            # load_value_quality_growth_metrics.py (stddev of trailing 4-quarter EPS growth
            # rates) and stored at 67.8% coverage. Still a genuinely dead fetch - it's a
            # dispersion metric (lower=more consistent), not a growth-rate on the same
            # higher-is-better scale as GROWTH_SCORE_FIELDS, so it isn't a candidate for the
            # 2026-08-28 multi-input restore below; fetched for reference/display only.
            # quarterly_growth_momentum/earnings_growth_4q_avg added 2026-08-28 (goal: restore
            # multi-input Growth blend - see GROWTH_SCORE_FIELDS/_score_growth): both computed
            # by _compute_quarterly_metrics in load_value_quality_growth_metrics.py (the loader
            # that runs in the local dev pipeline) and mirrored into BOTH growth_metrics and
            # quality_metrics by that same loader's _insert_growth_metrics/_insert_quality_metrics
            # (verified directly in that file's INSERT column lists, not assumed from an older
            # docstring here) - previously fetched here (quarterly_growth_momentum only) and
            # left completely unscored on a deliberate-but-since-overridden scope decision.
            # Read off growth_metrics's own copy here rather than merging in quality_metrics's -
            # both hold the same value, and every other GROWTH_SCORE_FIELDS candidate is already
            # a growth_metrics column, so this keeps _score_growth reading one dict, one table.
            #
            # forward_eps_growth_current_fy/forward_eps_growth_next_fy/forward_revenue_growth_next_fy
            # added 2026-08-31 (goal: growth-pillar industry-alignment review - see
            # GROWTH_SCORE_FIELDS below for the full rationale): forward/analyst-consensus EPS
            # growth is the headline Growth descriptor in MSCI/Russell/S&P's own published
            # methodologies and this repo's Growth blend was entirely backward-looking without
            # it. eps_estimate_revision_90d_pct fetched too but stays informational-only (a
            # revision-momentum signal, not a growth-rate level - not a GROWTH_SCORE_FIELDS
            # candidate).
            cur.execute(
                "SELECT symbol, revenue_growth_1y, revenue_growth_3y, revenue_growth_5y, "
                "eps_growth_1y, eps_growth_3y, eps_growth_5y, book_value_growth, "
                "net_income_growth_yoy, operating_income_growth_yoy, sustainable_growth_rate, "
                "fcf_growth_yoy, ocf_growth_yoy, "
                "gross_margin_trend, operating_margin_trend, net_margin_trend, roe_trend, asset_growth_yoy, "
                "eps_growth_stability, quarterly_growth_momentum, earnings_growth_4q_avg, "
                "forward_eps_growth_current_fy, forward_eps_growth_next_fy, forward_revenue_growth_next_fy, "
                "eps_estimate_revision_90d_pct, "
                "data_unavailable FROM growth_metrics"
            )
            self._growth_cache: dict[str, tuple[Any, ...]] = {row[0]: tuple(row[1:]) for row in cur.fetchall()}

            # forward_pe/ev_ebitda/ev_revenue added: loaded and displayed on the scores page
            # (migration 1191 backfilled ev_ebitda/ev_revenue/forward_pe onto sec_valuations,
            # copied into value_metrics by load_value_quality_growth_metrics.py) but never
            # read here before - zero influence on value_score.
            # margin_of_safety_pct added: DCF-based "discount to intrinsic value" (Value
            # factor goal, 2026-08-17) - computed by load_sec_valuations.py, copied onto
            # value_metrics by load_value_quality_growth_metrics.py, migration 1208.
            # market_cap added 2026-08-25 (goal: close the Size-factor gap found this pass -
            # see _score_value's docstring "SIZE FACTOR" section): already stored on
            # value_metrics (no schema change needed, 77.4% coverage), just never read here
            # before - zero influence on value_score until now.
            # pe_ratio_unavailable_reason/forward_pe_unavailable_reason added 2026-08-28
            # (goal: "is this value score right per industry best practice" - the E/P vs P/E
            # gap): live-confirmed 2283/2519 pe_ratio NULLs and 848/1560 forward_pe
            # "no_analyst_estimates" rows are actually unprofitable/negative-forecast-earnings
            # companies (real values, just not ratio-able), not missing data - see
            # _score_value's PE/Forward P/E blocks for how these are now used.
            cur.execute(
                "SELECT symbol, pe_ratio, pb_ratio, ps_ratio, peg_ratio, dividend_yield, fcf_yield, "
                "forward_pe, ev_ebitda, ev_revenue, margin_of_safety_pct, market_cap, net_payout_yield, "
                "pe_ratio_unavailable_reason, forward_pe_unavailable_reason, "
                "data_unavailable FROM value_metrics"
            )
            self._value_cache: dict[str, tuple[Any, ...]] = {row[0]: tuple(row[1:]) for row in cur.fetchall()}

            # amihud_illiquidity wiring REMOVED 2026-08-26 (user directive, same day it was
            # added - see _score_value's docstring for why: not a bug, a deliberate call that
            # an illiquidity-premium tilt isn't worth carrying in live scoring given this
            # system's own realistic execution-cost concerns for the exact names it would
            # favor). technical_data_daily.amihud_illiquidity itself is left computed/stored
            # (loaders/load_technical_indicators.py, migration 1232) - only its consumption
            # here was removed, same convention as EV/EBITDA/EV/Revenue elsewhere in this file.

            # positioning_metrics preload REMOVED 2026-08-27: Positioning retired as a
            # composite pillar (see BASE_PILLAR_WEIGHTS), so this loader no longer reads
            # positioning_metrics at all - the table itself, and its own loader
            # (load_positioning_metrics.py), are unaffected and keep populating it for the
            # scores API's informational positioning_inputs display.

            # downside_volatility_252d/max_drawdown_1y added: written by load_risk_metrics_daily.py
            # (migration 1184/1175) but never read here before.
            # FIX 2026-08-16: downside_volatility_60d/30d also added here - _score_stability has
            # scored them (7.5%/5% weight) since the "Fixed 2026-08-16: 60d/30d now scored too"
            # comment there, but this SELECT never fetched either column even though both already
            # exist on stability_metrics (same table, no new migration needed) - the two weight
            # slots were dead in every real score since that fix landed. Same bug class as
            # [[momentum_score_sma_dead_weight_fix_20260816]].
            # CLEANUP 2026-08-16 (later): debt_to_assets dropped from this SELECT - Stability no
            # longer scores it (moved to Quality, which reads its own debt_to_assets directly
            # from quality_metrics), so fetching it here was dead weight.
            cur.execute(
                "SELECT symbol, volatility_252d, volatility_60d, volatility_30d, beta, "
                "downside_volatility_252d, downside_volatility_60d, downside_volatility_30d, max_drawdown_1y, "
                "data_unavailable "
                "FROM stability_metrics"
            )
            self._stability_cache: dict[str, tuple[Any, ...]] = {row[0]: tuple(row[1:]) for row in cur.fetchall()}

            # CRITICAL FIX 2026-07-18: Read momentum from momentum_metrics table instead of computing from scratch
            # momentum_metrics is populated by load_risk_metrics_daily.py with precomputed momentum values
            cur.execute(
                "SELECT symbol, momentum_1m, momentum_3m, momentum_6m, momentum_12m, data_unavailable "
                "FROM momentum_metrics"
            )
            self._momentum_cache: dict[str, tuple[Any, ...]] = {row[0]: tuple(row[1:]) for row in cur.fetchall()}

            # Latest RSI/MACD per symbol, for momentum scoring (added: these were previously
            # only surfaced for display and had zero influence on momentum_score, which was
            # 100% price-return based). ROC is deliberately NOT pulled in here - it measures
            # the same thing as momentum_1m/3m/6m/12m (windowed % price return) and would just
            # double-weight that signal; RSI/MACD are qualitatively different (oscillator /
            # trend-confirmation) so they add real incremental information.
            # FIX 2026-08-16: also pull sma_50/sma_200/close so _get_momentum_metrics can
            # compute price_vs_sma_50/200 - _score_momentum has always had an 8%-weighted SMA
            # positioning component (and the scores dashboard has advertised it as a real
            # "used: true, 8% avg" input since the 2026-08-04 momentum audit), but this cache
            # never fetched sma_50/sma_200/close, so metrics.get(sma_field) was unconditionally
            # None for every symbol - 8% of the documented momentum_score formula was dead in
            # every real score computed. Unlike ROC above, SMA positioning is NOT a duplicate
            # signal of price-return momentum (it's price-vs-trend, not windowed % return), so
            # there's no double-weighting concern here.
            cur.execute(
                "SELECT DISTINCT ON (symbol) symbol, rsi_14, macd, sma_50, sma_200, close "
                "FROM technical_data_daily ORDER BY symbol, date DESC"
            )
            self._technical_cache: dict[str, tuple[Any, ...]] = {row[0]: tuple(row[1:]) for row in cur.fetchall()}

    def fetch_incremental(self, symbol: str, since: date | None) -> list[dict[str, Any]]:
        """Compute stock scores for this symbol. Returns data_unavailable dict if unable to compute.

        CRITICAL: At the PUBLIC API boundary, converts internal RuntimeError to explicit
        data_unavailable marker for operator visibility. Callers can distinguish:
        - None/empty returns: data genuinely unavailable (not an error)
        - Exception propagation: actual system failures (database, auth, etc.)

        CRITICAL FIX (Session 246): Ensure metric caches are initialized before computing scores.
        The _prepare_batch_context() method must be called before fetch_incremental() is invoked.
        Callers MUST initialize caches OR fail-fast with clear error message.
        """
        # CRITICAL: Check that batch context was prepared (caches initialized)
        if not hasattr(self, "_quality_cache"):
            raise RuntimeError(
                f"[STOCK_SCORES] CRITICAL: Batch context not initialized for {symbol}. "
                "The _prepare_batch_context() method must be called before fetch_incremental(). "
                "This is a framework contract violation - either the loader's run() method "
                "didn't call _prepare_batch_context(), or fetch_incremental() was called directly."
            )

        try:
            score_result = self._compute_stock_score(symbol)
            if not score_result:
                # This should not occur (internal _compute_stock_score raises on failure),
                # but safeguard against unexpected None returns
                logger.warning(f"[STOCK_SCORES] Unexpected None return for {symbol} - marking data unavailable")
                # Return explicit data_unavailable marker so symbol appears in DB with clear status
                return [
                    {
                        "symbol": symbol,
                        "composite_score": None,
                        "signal_score": None,
                        "quality_score": None,
                        "growth_score": None,
                        "value_score": None,
                        "momentum_score": None,
                        "risk_score": None,
                        "data_completeness": 0,
                        "data_unavailable": True,
                        "reason": "Internal scoring failure - unexpected None return",
                        "reason_type": "loader_failed",
                        "date": datetime.now(timezone.utc).date(),
                        "updated_at": datetime.now(timezone.utc),
                    }
                ]
            return [score_result]
        except (RuntimeError, ValueError) as e:
            # Upstream metric loaders insufficient data: return explicit data_unavailable marker
            # instead of empty list so symbol appears in DB with clear status flag
            logger.warning(f"[STOCK_SCORES] Cannot compute score for {symbol}: {e!s}")
            return [
                {
                    "symbol": symbol,
                    "composite_score": None,
                    "signal_score": None,
                    "quality_score": None,
                    "growth_score": None,
                    "value_score": None,
                    "momentum_score": None,
                    "risk_score": None,
                    "data_completeness": 0,
                    "data_unavailable": True,
                    "reason": str(e),
                    "reason_type": "loader_failed",
                    "date": datetime.now(timezone.utc).date(),
                    "updated_at": datetime.now(timezone.utc),
                }
            ]

    def _compute_stock_score(self, symbol: str) -> dict[str, Any]:
        """Compute composite stock score from REAL metrics only (no fake defaults).

        CRITICAL: Fails fast if stock has insufficient real data (>=50% completeness required).
        Do not return None or fake markers - callers must know immediately if scoring failed.

        Returns dict with keys: symbol, composite_score, quality_score, growth_score,
        value_score, momentum_score, risk_score, rs_percentile, data_completeness

        Raises:
            RuntimeError: If insufficient metrics available to compute valid score
        """
        try:
            with DatabaseContext("read") as cur:
                quality = self._get_quality_metrics(cur, symbol)
                growth = self._get_growth_metrics(cur, symbol)
                value = self._get_value_metrics(cur, symbol)
                risk_metrics = self._get_stability_metrics(cur, symbol)
                momentum = self._get_momentum_metrics(cur, symbol)

            # Compute individual factor scores from REAL data only (no defaults)
            # Scoring functions return float or dict (marker when data unavailable)
            # Keep marker dicts throughout to track missing data reasons
            quality_score = self._score_quality(quality, symbol)
            growth_score = self._score_growth(growth, symbol)
            value_score = self._score_value(value, symbol)
            risk_score = self._score_risk(risk_metrics, symbol)
            momentum_score = self._score_momentum(momentum, symbol)

            # Extract numeric scores for computation, track unavailability reasons
            def is_real_score(result: float | dict[str, Any] | None) -> bool:
                return isinstance(result, float)

            def get_marker_reason(result: float | dict[str, Any] | None) -> str:
                if isinstance(result, dict) and result.get("data_unavailable"):
                    reason = result.get("reason")
                    if isinstance(reason, str):
                        return reason
                return "unknown_reason"

            # Count data completeness: only float scores count as "real data"
            # Markers (dicts with data_unavailable=True) are excluded from count
            # Session 260: Momentum loader now fixed and included in completeness calculation
            # 5 pillars are evaluated: quality, growth, value, risk, momentum (Positioning
            # retired as a composite pillar 2026-08-27; Size retired as a composite pillar
            # 2026-08-28 - see BASE_PILLAR_WEIGHTS)
            # Minimum 70% completeness (3.5/5 metrics) required per GOVERNANCE.md
            all_scores = {
                "quality": quality_score,
                "growth": growth_score,
                "value": value_score,
                "risk": risk_score,
                "momentum": momentum_score,
            }
            real_scores = [s for s in all_scores.values() if is_real_score(s)]
            data_count = len(real_scores)
            unavailable_metrics = {
                name: get_marker_reason(score) for name, score in all_scores.items() if not is_real_score(score)
            }

            # CRITICAL FIX 2026-07-19: Log when scores computed with <5 metrics for visibility.
            # Traders need to see completeness % in dashboards to filter based on GOVERNANCE entry gates.
            if data_count < 5 and data_count >= 4:
                missing = sorted([k for k, v in all_scores.items() if not is_real_score(v)])
                logger.info(
                    f"[STOCK_SCORES] {symbol}: Score computed with {data_count}/5 metrics ({100.0 * data_count / 5:.1f}% complete). "
                    f"Missing: {', '.join(missing)}. Trading filter gate: completeness >= 70% per GOVERNANCE."
                )
            elif data_count < 4:
                missing = sorted([k for k, v in all_scores.items() if not is_real_score(v)])
                logger.warning(
                    f"[STOCK_SCORES] {symbol}: Score computed with {data_count}/5 metrics ({100.0 * data_count / 5:.1f}% complete). "
                    f"Minimum 4 metrics ensures diversity against single-metric bias."
                )

            # NUMERIC(4,2) schema constraint: max 99.99 (not 100.0)
            # Calculate completeness on 5 pillars (quality, growth, value, risk, momentum)
            data_completeness = min(99.99, round((data_count / 5.0) * 100, 2))

            # CRITICAL FIX 2026-07-19: Compute score for all symbols with 5+/6 metrics, mark completeness for trading filters.
            # Previous: Rejected any score with <70% completeness, removing 1,635 valid candidates from universe.
            # New: Calculate scores for all candidates with sufficient diversity (5+ metrics), let trading logic
            # (entry gates) filter based on completeness %. This gives traders full visibility + control.
            # GOVERNANCE.md says: "Signals < 70% completeness are excluded from scoring" (trading exclusion, not computation exclusion).
            # The minimum 5 metrics check below ensures sufficient diversity to prevent single-metric bias.
            # Completeness % is still tracked and reported for operator/trader visibility.

            # Session 530: Enable degraded-mode scoring for SPACs/new listings
            # Previously: required minimum 2/6 metrics, silently rejected 8 SPACs
            # Now: allow 1+ metrics for degraded scoring, marked with low completeness % in DB
            # Trading gates still filter on completeness >= 70%, so degraded scores won't enter live signals
            # min_required_metrics lowered from 3 to 1 to make "no data" stocks visible with reason codes
            min_required_metrics = 1

            if data_count < min_required_metrics:
                raise RuntimeError(
                    f"[STOCK_SCORES] {symbol}: CRITICAL - zero metrics available. "
                    f"Got {data_count}/5 metrics. Cannot compute score with no metric data."
                )

            # GOVERNANCE COMPLIANCE: Compute scores with 4+/5 metrics (sufficient diversity).
            # No weight redistribution fallbacks (normalized weights stay fixed).
            # Trading gates will filter based on completeness % >= 70% per GOVERNANCE.md line 62.
            # Reason: Rejecting a few-metric-short score wastes valid signals; incomplete data is honest data marked visible.

            score_availability = {
                "quality": is_real_score(quality_score),
                "growth": is_real_score(growth_score),
                "value": is_real_score(value_score),
                "risk": is_real_score(risk_score),
                "momentum": is_real_score(momentum_score),
            }

            real_metric_count = sum(1 for v in score_availability.values() if v)

            # DEGRADED MODE: Allow scoring with 1+ metrics for SPACs/new listings
            # Session 530 (2026-08-05): Enable degraded-mode scoring for SPACs with insufficient SEC data.
            # Previously: rejected scores with <2 metrics, leaving 8 SPACs (APMD, BANL, etc) with NULL scores.
            # New: allow 1+ metrics for degraded scoring, marked clearly in DB with low completeness %.
            # Trading gates still filter on completeness >= 70%, so degraded scores won't enter live signals.
            # This makes "no data" stocks visible in dashboard with reason codes instead of disappearing.
            if real_metric_count < 1:
                missing_metrics = [k for k, v in score_availability.items() if not v]
                logger.error(
                    f"[STOCK_SCORES] {symbol}: CRITICAL - zero real metrics available. "
                    f"Available {real_metric_count}/5. "
                    f"Missing: {', '.join(missing_metrics)}. "
                    f"Cannot compute even degraded score without any real data."
                )
                raise ValueError(
                    f"{symbol}: zero metrics ({real_metric_count}/5, impossible to score). "
                    f"Cannot compute score with zero available metrics."
                )

            if real_metric_count < 2:
                # Degraded mode: score with 1 metric only (for SPACs/new listings)
                logger.info(
                    f"[STOCK_SCORES] {symbol}: DEGRADED MODE - {real_metric_count}/5 metrics available. "
                    f"Computing partial score (dashboard will show data_completeness={int(real_metric_count / 5 * 100)}%)"
                )

            # Fixed base weights (no redistribution per GOVERNANCE fail-fast rule)
            # Unavailable metrics contribute 0 to composite (their weight is skipped, lost).
            # This means composite score is 0-100 scale, where:
            # - 100 = all 5 metrics perfect
            # - 50 with all 5 = truly 50/100
            # - 50 with only some pillars available = an incomplete picture (only the available
            #   pillars' weight contributed; missing pillars' weight is simply not counted)
            # Dashboard displays completeness % so traders see data quality.
            #
            # RESOLVED 2026-08-25 (goal: re-audit ALL stock_scores inputs, including whether
            # the pillar LIST itself is complete, and finally close out the "underpowered,
            # not acted on" composite-weight question below). These 6 percentages have no
            # documented empirical basis anywhere in this file - just hand-set numbers. Built
            # algo/research/fama_macbeth_composite_weights.py to test them via Grinold & Kahn's
            # "Active Portfolio Management" combining-alphas methodology (regression-weight
            # signals by realized predictive power controlling for correlation among them -
            # exactly what multivariate Fama-MacBeth does).
            #
            # CONCURRENT INDEPENDENT RECONSTRUCTION (2026-08-25, merge note): this exact
            # composite-weights fix was worked on by two parallel sessions at once after an
            # earlier attempt was lost to an uncommitted-work race (see
            # [[composite_weights_reweighted_size_factor_reconfirmed_20260825]] /
            # [[stock_scores_composite_weights_reconstruction_after_lost_commit_20260826]]).
            # The other session's independent re-run found stability_proxy t=2.70/value_proxy
            # t=2.05 multivariate (both clearing |t|=2) - slightly stronger than this session's
            # own t=1.91/1.39 below, most likely from minor sample/construction differences
            # (this version additionally fixes the PE/PB/PS-within-Value selection bias, see
            # below, which the other session's value_proxy didn't include). Both independently
            # reached the identical qualitative conclusion and the identical reweight numbers -
            # convergent evidence the direction is real, not an artifact of either session's
            # specific methodology choices.
            #
            # FIRST PASS (same day, earlier): required all 6 pillar proxies non-null per
            # symbol-month (strict dropna()) - only kept the intersection of annual-fundamentals
            # coverage (growth/value/quality) AND full price-history coverage (stability/
            # momentum/positioning): 109 months, median 850 symbols, likely biased toward
            # larger/more-established names. value_proxy came out strongest (t=1.78 multivariate/
            # 1.83 univariate, still short of conventional significance); stability/momentum
            # came back negatively signed, opposite their own single-pillar-test signs -
            # suspected selection-bias artifact. Underpowered; not acted on.
            #
            # REDESIGNED PASS (same day, later): relaxed the all-6-required rule - only
            # forward return is mandatory; each pillar proxy is z-scored over whatever's
            # actually available that month, then missing pillars are imputed to 0 (the
            # z-scored mean), matching this exact base_weights loop's own "skip unavailable,
            # renormalize over what's present" tolerance rather than an artificially strict
            # test. Result: 110 months (2017-2026), median cross-section jumped from 850 to
            # 6,505 symbols (7.6x) - a materially less selective sample. Also caught and fixed
            # two staleness bugs in the proxy construction itself before trusting the result:
            # value_proxy still used the pre-audit EV/EBITDA+EV/Revenue split (removed from the
            # live formula as PE/PS duplicates the same day) instead of the live formula's
            # actual PE/PB/PS/FCF/dividend/Size mix, and momentum_proxy still used the
            # pre-redesign mom_6m/mom_12m split (replaced live by the derived 12-1 skip-month
            # construction) instead of mom_3m/mom_12_1/RSI/MACD/SMA - both fixed to match
            # current live weights before this test's numbers were trusted.
            #
            # Multivariate (controlling for the other 5): stability_proxy t=1.91, value_proxy
            # t=1.39, growth_proxy t=1.16, positioning_proxy t=0.82, quality_proxy t=0.81,
            # momentum_proxy t=-0.87 (negatively signed). Univariate: value_proxy t=1.60,
            # stability_proxy t=1.31, quality_proxy t=1.22, growth_proxy t=0.81,
            # positioning_proxy t=0.23, momentum_proxy t=0.05. No pillar clears the
            # conventional |t|=2 significance bar in this run, but Stability and Value are
            # consistently the two strongest across both specs, while Momentum (negatively
            # signed both ways) and Positioning (weak both ways, consistent with
            # ad_rating's already-documented null finding - see this file's Positioning
            # docstring) are consistently the two weakest. ACTED ON with a proportionate
            # reweight (not a full rewrite, given no pillar reaches clean significance):
            # stability 0.14->0.18 (+4, strongest multivariate showing, consistent with this
            # pillar's own volatility_60d being the single strongest sub-factor found in the
            # entire multi-pillar audit), value 0.20->0.21 (+1, clear univariate leader),
            # momentum 0.15->0.12 (-3, negatively signed both specs, consistent with this
            # pillar's own sub-factors also testing null), positioning 0.14->0.12 (-2,
            # consistent with ad_rating's own t=-0.23 null result), growth/quality left
            # unchanged (0.12/0.25 - more ambiguous multivariate-vs-univariate showings, no
            # clear case for moving either direction beyond what their own within-pillar
            # audits already did).
            #
            # SIZE FACTOR (market cap) - retired entirely 2026-08-28 (user directive: "just
            # get rid of size"). See BASE_PILLAR_WEIGHTS' own comment for the full history and
            # evidence trail - not repeated here. BASE_PILLAR_WEIGHTS above is a 5-pillar dict
            # again (quality/growth/value/risk/momentum).
            # Clamp scores to 0-100, keep markers for missing data
            def clamp_score(score: float | dict[str, Any] | None) -> float | dict[str, Any] | None:
                if isinstance(score, float):
                    return max(0.0, min(100.0, score))
                # Return marker dicts as-is; don't silence them with None
                return score if isinstance(score, dict) else None

            clamped_quality = clamp_score(quality_score)
            clamped_growth = clamp_score(growth_score)
            clamped_value = clamp_score(value_score)
            clamped_risk = clamp_score(risk_score)
            clamped_momentum = clamp_score(momentum_score)

            # VALUE x RISK INTERACTION: see VALUE_RISK_INTERACTION_MAX_SHIFT's module-level
            # docstring for the evidence. Conditions Value's/Risk's own weights on THIS symbol's
            # real risk_score (falls back to unmodified base weights if Risk is unavailable, same
            # as clamped_risk being None below).
            normalized_weights = _value_risk_adjusted_weights(clamped_risk if isinstance(clamped_risk, float) else None)

            # Composite: only use metrics that are actually available
            # Do NOT redistribute weights (GOVERNANCE rule: no weight redistribution)
            # If metric unavailable, its weight is skipped (contributes 0), not given to other metrics
            composite_score_value = 0.0
            for metric_name, clamped_value_score in [
                ("quality", clamped_quality),
                ("growth", clamped_growth),
                ("value", clamped_value),
                ("risk", clamped_risk),
                ("momentum", clamped_momentum),
            ]:
                # Only use base weight if metric is available
                # CRITICAL: Require explicit availability flag for each metric (fail-fast if missing)
                if metric_name not in score_availability:
                    raise ValueError(
                        f"[STOCK_SCORES] {symbol}: availability flag missing for '{metric_name}' metric. "
                        f"All metrics must have explicit availability status in score_availability dict."
                    )
                if not score_availability[metric_name]:
                    continue  # Skip unavailable metrics (don't give their weight to others)

                weight = normalized_weights[metric_name]
                # Handle marker dicts (data unavailable) separately from float scores
                if isinstance(clamped_value_score, dict) and clamped_value_score.get("data_unavailable"):
                    # Marker returned - data unavailable for this metric
                    # CRITICAL: Validate reason field exists when data_unavailable=True (fail-fast if missing)
                    reason = clamped_value_score.get("reason")
                    if reason is None:
                        raise ValueError(
                            f"[STOCK_SCORES] {symbol} metric '{metric_name}' marked data_unavailable but missing required 'reason' field. "
                            f"API contract violation: unavailable markers must include reason. Marker: {clamped_value_score}"
                        )
                    unavailable_metrics[metric_name] = reason
                    logger.warning(f"[STOCK_SCORES] {metric_name} unavailable for {symbol}: {reason}")
                elif clamped_value_score is None:
                    raise ValueError(
                        f"[{symbol}] Metric '{metric_name}' has weight {weight:.3f} but returned None (not a marker dict). "
                        "This indicates a calculation error or incomplete implementation."
                    )
                elif isinstance(clamped_value_score, float):
                    composite_score_value += clamped_value_score * weight
                else:
                    raise RuntimeError(
                        f"[{symbol}] Metric '{metric_name}' returned unexpected type {type(clamped_value_score).__name__}. "
                        "Expected float or dict marker."
                    )

            # Clamp to 0-100: raw composite value (may be <100 if metrics missing).
            # No rescaling per GOVERNANCE (no weight redistribution).
            # Traders see completeness % to understand data quality.
            composite_score = max(0.0, min(100.0, round(composite_score_value, 2)))

            def extract_score_value(score_result: float | dict[str, Any] | None) -> float | None:
                """Extract numeric score from result (float or marker dict)."""
                if isinstance(score_result, float):
                    return round(score_result, 2)
                return None  # Markers and None return as None

            # CRITICAL FIX: Enforce completeness threshold per GOVERNANCE.md + config
            # Session 297 assumed "trading gates will filter", but no downstream filters exist.
            # Database audit found 851 scores with 50-70% completeness marked available=FALSE.
            # This violates fail-fast governance: incomplete data must be marked unavailable.
            # Threshold is now configurable via algo_config.min_completeness_score (default: 70%)
            # Read threshold from cache that was loaded in _prepare_batch_context()
            min_completeness_threshold = getattr(self, "_min_completeness_threshold", 70.0)

            score_available = data_completeness >= min_completeness_threshold
            if not score_available:
                reason_text = f"Completeness {data_completeness:.2f}% < {min_completeness_threshold}% threshold (missing metrics: {', '.join(unavailable_metrics.keys())})"
            else:
                reason_text = None

            # Build components breakdown for dashboard display
            components = {
                "quality": extract_score_value(clamped_quality),
                "growth": extract_score_value(clamped_growth),
                "value": extract_score_value(clamped_value),
                "risk": extract_score_value(clamped_risk),
                "momentum": extract_score_value(clamped_momentum),
            }

            # Build data sources attribution for transparency
            data_sources = {
                "quality": ["financial_statements", "sec_valuations"] if extract_score_value(clamped_quality) else [],
                "growth": ["financial_statements", "analyst_earnings_estimates", "enhanced_quality_growth_metrics"]
                if extract_score_value(clamped_growth)
                else [],
                "value": ["financial_statements", "sec_valuations", "dividend_data"]
                if extract_score_value(clamped_value)
                else [],
                "risk": ["risk_metrics_daily", "technical_data_daily", "financial_statements"]
                if extract_score_value(clamped_risk)
                else [],
                "momentum": ["technical_data_daily", "market_status_daily", "insider_transaction_velocity"]
                if extract_score_value(clamped_momentum)
                else [],
            }

            # POSITIONING FULLY RETIRED 2026-08-27, SIZE FULLY RETIRED 2026-08-28 (see
            # BASE_PILLAR_WEIGHTS for the full evidence trail on both). Neither positioning_score
            # nor size_score appears anywhere in this function anymore: not in
            # all_scores/score_availability/the composite loop/components/data_sources, and not
            # in this result dict or snapshot_score_history()'s INSERT below. Positioning's A/D
            # rating, institutional ownership, and short interest are unaffected upstream -
            # load_positioning_metrics.py keeps computing/storing them for the scores API's
            # informational positioning_inputs display; this loader just no longer reads or
            # scores them. Size's market_cap likewise keeps being computed/stored on
            # value_metrics unaffected - this loader just no longer synthesizes a size_score
            # from it.
            result = {
                "symbol": symbol,
                "composite_score": composite_score,
                "quality_score": extract_score_value(clamped_quality),
                "growth_score": extract_score_value(clamped_growth),
                "value_score": extract_score_value(clamped_value),
                "momentum_score": extract_score_value(clamped_momentum),
                "risk_score": extract_score_value(clamped_risk),
                # Placeholder only: update_rs_percentiles() (post_run(), batch rank pass)
                # overwrites this with the real PERCENT_RANK() value for every symbol once the
                # whole run succeeds. NULL here (not 0.0) so that if post_run() is skipped -
                # runner.py only calls it after the fail-rate gate passes - or the run crashes
                # first, rows are left visibly missing their RS percentile rather than showing
                # a fabricated bottom-percentile score indistinguishable from a real 0th-percentile
                # stock (this fed straight into Phase 7's signal-generation completeness gate).
                "rs_percentile": None,
                "data_completeness": data_completeness,
                "unavailable_metrics": json.dumps(unavailable_metrics) if unavailable_metrics else None,
                "components": json.dumps(components),  # Score component breakdown
                "data_sources": json.dumps(data_sources),  # Data source attribution
                "data_unavailable": not score_available,  # CRITICAL: Mark unavailable if completeness < 70%
                "reason": reason_text,
                # reason_type ADDED 2026-09-01 (/goal session, "make sure results make sense"
                # investigation). This dict is written on every non-exceptional pass through
                # _compute_stock_score, but previously never included "reason_type" at all -
                # only fetch_incremental's two exception-handling branches set it, to
                # "loader_failed". Since BulkInsertManager derives each row's UPSERT column
                # list from that row's own dict keys (see bulk_insert_manager.py), a symbol
                # that failed once (reason_type='loader_failed' persisted) and later recovered
                # never had reason_type in its column list on the recovery write - the stale
                # 'loader_failed' value was silently carried forward FOREVER, untouched by
                # every subsequent successful re-score. Live-confirmed 2026-09-01: symbols
                # (including NVDA, BRK.A, BRK.B, BYND) sat at reason_type='loader_failed'
                # despite full completeness and real scored pillars - a false-failure signal
                # that would mislead exactly this kind of "why is data missing" triage. Always
                # writing "unknown" here (this loader's own reason_text messages are plain
                # completeness-threshold strings, never the "loader_failed:"/"not_applicable:"/
                # "unavailable_temporary:" prefixes utils/loaders/unavailable_markers.py's
                # extract_reason_type() checks for for other loaders' governance markers, so it
                # would resolve to "unknown" here regardless) matches the column's own DEFAULT
                # and every other successful row already in the table - it just also now
                # actively RESETS a stale 'loader_failed' on recovery instead of leaving it out
                # of the write entirely.
                "reason_type": "unknown",
                "date": datetime.now(timezone.utc).date(),
                "updated_at": datetime.now(timezone.utc),
            }
            if unavailable_metrics:
                logger.warning(
                    f"[STOCK_SCORES] {symbol} computed with degraded metrics: "
                    f"{', '.join(f'{k}={v}' for k, v in unavailable_metrics.items())}"
                )
            return result

        except Exception as e:
            raise RuntimeError(f"Operation failed: {e}") from e

    # ARCHITECTURAL PATTERN: Internal Scoring Pipeline (UPDATED 2026-07-03)
    # ====================================================
    # The following _get_* and _score_* methods are INTERNAL PLUMBING that feeds into
    # _compute_stock_score() → fetch_incremental() public API.
    #
    # RETURN TYPES (STRICT):
    # - All 6 _get_*() methods return dict[str, Any] (either real metrics or data_unavailable marker)
    # - All 6 _score_*() methods return float | dict[str, Any] (score or data_unavailable marker)
    # - No None returns anywhere - either real data or explicit data_unavailable marker
    # - Marker dicts always have {"data_unavailable": True, "reason": "..."}
    #
    # FIELD CONVERSION (CRITICAL SAFETY):
    # - All numeric fields converted via safe_float() (never raw float())
    # - safe_float() raises RuntimeError on type conversion failure
    # - Prevents data corruption from propagating silently
    # - Every field conversion distinguishes None (no data) from ValueError (corrupted data)
    #
    # DATA VALIDATION (FAIL-FAST):
    # - All _get_* functions validate row length before accessing indices (6 bound checks)
    #   * _get_quality_metrics: 24 columns (roe through revenue_growth_yoy, includes Phase 3 expansion fields)
    #   * _get_growth_metrics: 12 columns (revenue_growth_1y through ocf_growth_yoy, data_unavailable last)
    #   * _get_value_metrics: 15 columns (pe_ratio through forward_pe_unavailable_reason, data_unavailable last)
    #   * _get_stability_metrics: 8 columns (volatility_252d through max_drawdown_1y, data_unavailable last)
    #   * _get_momentum_metrics: 5 columns (current through price_12m_ago)
    # - All _score_* functions return marker dicts if input metrics are missing/incomplete
    # - Momentum metrics: Require proper lookback periods (30d/60d/120d/252d), not degraded estimates
    # - Stock minimum: 1/6 metrics (degraded-mode scoring allowed); trading gates separately
    #   filter on data_completeness >= 70% regardless of stock age (no IPO exceptions there)
    #
    # MARKER HANDLING by _compute_stock_score():
    # - real_scores = [s for s in all_scores if isinstance(s, float)] → only floats count
    # - score_availability dict tracks which metrics returned markers
    # - Weight redistribution: Available metrics upweighted, missing metrics zeroed
    # - Minimum check: raise RuntimeError if data_count < 3 (hard threshold)
    #
    # PUBLIC API (Exceptions, not degraded returns):
    # - fetch_incremental() raises RuntimeError on insufficient metrics (no silent degradation)
    # - Returns data_unavailable dict to DB only on exceptions (operator visibility)
    #
    # KEY CHANGES (2026-07-03):
    # 1. All _get_* now validate row length before accessing (6 bound checks x 1-5 fields = 15+ validations)
    # 2. All numeric conversions use safe_float() consistently (prevents type corruption)
    # 3. Removed new-listing exception that allowed 2/6 metrics
    # 4. Removed short-term momentum fallback (2/4/7/14 day lookbacks violated standards)
    # 5. Type hints: Removed | None from _score_* returns (always float or dict)
    # 6. Updated all docstrings with MINIMUM DATA REQUIREMENT sections
    # ====================================================

    def _get_quality_metrics(self, cur: Any, symbol: str) -> dict[str, Any]:
        """Fetch quality metrics for symbol including Phase 3 expansion metrics.

        Returns explicit marker dict if data is unavailable (either no row or data_unavailable=True).
        Raises RuntimeError on database errors or data type mismatches.

        VALIDATION RULES:
        - Row length validation: Must have 24 columns (10 base + 14 Phase 3 expansion)
        - Schema mismatch (len(row) < 24) → raises ValueError immediately
        - All numeric fields converted via safe_float() (detects data corruption)
        - data_unavailable=True flag → returns marker dict even if row exists
        - No row at all → returns marker dict with reason="no_quality_metrics_found"

        CRITICAL FIX 2026-07-23 (Session 359): Now fetches all Phase 3 expansion fields
        (gross_margin, ebitda_margin, roic_pct, fcf_to_net_income, ocf_to_net_income, payout_ratio,
        free_cash_flow, operating_cash_flow, total_debt, total_cash, cash_per_share, ebitda,
        earnings_growth_yoy, revenue_growth_yoy, interest_coverage). CORRECTED 2026-08-26:
        `_enhance_quality_score()` this comment referenced no longer exists - it was replaced
        entirely by `_score_quality`'s current weighted composite (see that method's own
        docstring for the current formula). Of this list, payout_ratio and interest_coverage
        are real weighted inputs in that composite today; roic_pct/fcf_to_net_income and the
        rest were tested and excluded (no independent signal) or are fetched for reference/
        display only - not all of them feed quality_score.

        MINIMUM DATA REQUIREMENT: Row must have exactly 25 columns. Missing columns causes immediate
        fail-fast ValueError to prevent silent data corruption.
        """
        row = self._quality_cache.get(symbol)
        if row:
            # CRITICAL: Validate row has expected 25 columns before accessing indices
            # (10 original + 14 Phase 3 expansion + 1 interest_coverage + 1 data_unavailable flag = 26 total, minus symbol = 25)
            if len(row) < 25:
                raise ValueError(
                    f"[STOCK_SCORES] {symbol}: quality_metrics row has {len(row)} columns, expected 25. "
                    f"Schema mismatch detected - Phase 3 or interest_coverage fields missing. Failing fast."
                )
            data_unavailable = row[9]
            quality_score = safe_float(row[8], f"{symbol}.quality_score")
            # If marked unavailable, return marker even if row exists
            if data_unavailable:
                logger.debug(
                    f"[LOAD_STOCK_SCORES] {symbol} marked data_unavailable in quality_metrics "
                    f"(likely REIT or security with missing SEC filings)"
                )
                return marker_not_applicable(symbol, "quality_metrics")
            # Row exists and data is available - return all fields including Phase 3 expansion
            return {
                "roe": safe_float(row[0], f"{symbol}.roe"),
                "roa": safe_float(row[1], f"{symbol}.roa"),
                "operating_margin": safe_float(row[2], f"{symbol}.operating_margin"),
                "net_margin": safe_float(row[3], f"{symbol}.net_margin"),
                "debt_to_equity": safe_float(row[4], f"{symbol}.debt_to_equity"),
                "current_ratio": safe_float(row[5], f"{symbol}.current_ratio"),
                "quick_ratio": safe_float(row[6], f"{symbol}.quick_ratio"),
                "debt_to_assets": safe_float(row[7], f"{symbol}.debt_to_assets", allow_none=True),
                "quality_score": quality_score,  # Pre-computed by load_value_quality_growth_metrics.py
                # Phase 3 expansion metrics (Session 358+)
                "gross_margin": safe_float(row[10], f"{symbol}.gross_margin", allow_none=True),
                "ebitda_margin": safe_float(row[11], f"{symbol}.ebitda_margin", allow_none=True),
                "roic_pct": safe_float(row[12], f"{symbol}.roic_pct", allow_none=True),
                "fcf_to_net_income": safe_float(row[13], f"{symbol}.fcf_to_net_income", allow_none=True),
                "ocf_to_net_income": safe_float(row[14], f"{symbol}.ocf_to_net_income", allow_none=True),
                "payout_ratio": safe_float(row[15], f"{symbol}.payout_ratio", allow_none=True),
                "free_cash_flow": safe_float(row[16], f"{symbol}.free_cash_flow", allow_none=True),
                "operating_cash_flow": safe_float(row[17], f"{symbol}.operating_cash_flow", allow_none=True),
                "total_debt": safe_float(row[18], f"{symbol}.total_debt", allow_none=True),
                "total_cash": safe_float(row[19], f"{symbol}.total_cash", allow_none=True),
                "cash_per_share": safe_float(row[20], f"{symbol}.cash_per_share", allow_none=True),
                "ebitda": safe_float(row[21], f"{symbol}.ebitda", allow_none=True),
                "earnings_growth_yoy": safe_float(row[22], f"{symbol}.earnings_growth_yoy", allow_none=True),
                "revenue_growth_yoy": safe_float(row[23], f"{symbol}.revenue_growth_yoy", allow_none=True),
                "interest_coverage": safe_float(row[24], f"{symbol}.interest_coverage", allow_none=True),
            }
        # No row exists at all
        logger.warning(
            f"[LOAD_STOCK_SCORES] No quality metrics available for {symbol} - score completeness will be reduced"
        )
        return marker_loader_failed(symbol, "no_quality_metrics", "Quality metrics table missing data")

    def _get_growth_metrics(self, cur: Any, symbol: str) -> dict[str, Any]:
        """Fetch growth metrics for symbol.

        Returns explicit marker dict if data is unavailable (either no row or data_unavailable=True).
        Raises RuntimeError on database errors or data type mismatches.

        VALIDATION RULES:
        - Row length validation: Must have 25 columns (revenue_growth_1y/3y/5y, eps_growth_1y/
          3y/5y, book_value_growth, net_income_growth_yoy, operating_income_growth_yoy,
          sustainable_growth_rate, fcf_growth_yoy, ocf_growth_yoy, gross/operating/net_margin_
          trend, roe_trend, asset_growth_yoy, eps_growth_stability, quarterly_growth_momentum,
          earnings_growth_4q_avg, forward_eps_growth_current_fy, forward_eps_growth_next_fy,
          forward_revenue_growth_next_fy, eps_estimate_revision_90d_pct, data_unavailable) -
          extended 2026-08-31 to add the 4 forward/analyst-estimate fields (see
          GROWTH_SCORE_FIELDS/_score_growth for why 3 of the 4 now feed growth_score).
        - Schema mismatch (len(row) < 25) → raises ValueError immediately
        - All numeric fields converted via safe_float() (detects data corruption)
        - data_unavailable=True flag → returns marker dict even if row exists
        - No row at all → returns marker dict with reason="no_growth_metrics_found"

        CRITICAL FIX 2026-07-01: Now checks data_unavailable flag. Some securities have rows
        marked data_unavailable=True with NULL values. Previously returned NULLs instead of
        marker; now properly returns marker dict.

        MINIMUM DATA REQUIREMENT: Row must have exactly 25 columns. Missing columns causes
        immediate fail-fast ValueError. Dependent on upstream annual_income_statement availability.
        """
        row = self._growth_cache.get(symbol)
        if row:
            # CRITICAL: Validate row has expected 25 columns before accessing indices
            # (21 + forward_eps_growth_current_fy/next_fy + forward_revenue_growth_next_fy +
            # eps_estimate_revision_90d_pct, added 2026-08-31)
            if len(row) < 25:
                raise ValueError(
                    f"[STOCK_SCORES] {symbol}: growth_metrics row has {len(row)} columns, expected 25. "
                    f"Schema mismatch detected - cannot safely access data. Failing fast."
                )
            data_unavailable = row[24]
            # If marked unavailable, return marker even if row exists
            if data_unavailable:
                logger.debug(
                    f"[LOAD_STOCK_SCORES] {symbol} marked data_unavailable in growth_metrics "
                    f"(likely security with missing SEC filings)"
                )
                return marker_not_applicable(symbol, "growth_metrics")

            def _scale_fraction_to_pct(val: float | None) -> float | None:
                """forward_eps_growth_current_fy/next_fy and forward_revenue_growth_next_fy are
                stored as raw fractions (0.18 = 18%), unlike every other GROWTH_SCORE_FIELDS
                candidate which is already percentage-point scaled - _score_single_growth's
                cap=30 curve is calibrated for percentage-point inputs. Live-verified against
                the DB directly (not assumed from the column name): AAPL's real
                forward_eps_growth_next_fy=0.0816, not 8.16.
                """
                return val * 100 if val is not None else None

            # Row exists and data is available
            return {
                "revenue_growth_1y": safe_float(row[0], f"{symbol}.revenue_growth_1y"),
                "revenue_growth_3y": safe_float(row[1], f"{symbol}.revenue_growth_3y"),
                "revenue_growth_5y": safe_float(row[2], f"{symbol}.revenue_growth_5y"),
                "eps_growth_1y": safe_float(row[3], f"{symbol}.eps_growth_1y"),
                "eps_growth_3y": safe_float(row[4], f"{symbol}.eps_growth_3y"),
                "eps_growth_5y": safe_float(row[5], f"{symbol}.eps_growth_5y"),
                "book_value_growth": safe_float(row[6], f"{symbol}.book_value_growth", allow_none=True),
                "net_income_growth_yoy": safe_float(row[7], f"{symbol}.net_income_growth_yoy", allow_none=True),
                "operating_income_growth_yoy": safe_float(
                    row[8], f"{symbol}.operating_income_growth_yoy", allow_none=True
                ),
                "sustainable_growth_rate": safe_float(row[9], f"{symbol}.sustainable_growth_rate", allow_none=True),
                "fcf_growth_yoy": safe_float(row[10], f"{symbol}.fcf_growth_yoy", allow_none=True),
                "ocf_growth_yoy": safe_float(row[11], f"{symbol}.ocf_growth_yoy", allow_none=True),
                "gross_margin_trend": safe_float(row[12], f"{symbol}.gross_margin_trend", allow_none=True),
                "operating_margin_trend": safe_float(row[13], f"{symbol}.operating_margin_trend", allow_none=True),
                "net_margin_trend": safe_float(row[14], f"{symbol}.net_margin_trend", allow_none=True),
                "roe_trend": safe_float(row[15], f"{symbol}.roe_trend", allow_none=True),
                "asset_growth_yoy": safe_float(row[16], f"{symbol}.asset_growth_yoy", allow_none=True),
                "eps_growth_stability": safe_float(row[17], f"{symbol}.eps_growth_stability", allow_none=True),
                "quarterly_growth_momentum": safe_float(
                    row[18], f"{symbol}.quarterly_growth_momentum", allow_none=True
                ),
                "earnings_growth_4q_avg": safe_float(row[19], f"{symbol}.earnings_growth_4q_avg", allow_none=True),
                "forward_eps_growth_current_fy": _scale_fraction_to_pct(
                    safe_float(row[20], f"{symbol}.forward_eps_growth_current_fy", allow_none=True)
                ),
                "forward_eps_growth_next_fy": _scale_fraction_to_pct(
                    safe_float(row[21], f"{symbol}.forward_eps_growth_next_fy", allow_none=True)
                ),
                "forward_revenue_growth_next_fy": _scale_fraction_to_pct(
                    safe_float(row[22], f"{symbol}.forward_revenue_growth_next_fy", allow_none=True)
                ),
                "eps_estimate_revision_90d_pct": safe_float(
                    row[23], f"{symbol}.eps_estimate_revision_90d_pct", allow_none=True
                ),
            }
        # No row exists at all
        logger.warning(
            f"[LOAD_STOCK_SCORES] No growth metrics available for {symbol} - score completeness will be reduced"
        )
        return marker_loader_failed(symbol, "no_growth_metrics", "Growth metrics table missing data")

    def _get_value_metrics(self, cur: Any, symbol: str) -> dict[str, Any]:
        """Fetch value metrics for symbol.

        Returns explicit marker dict if data is unavailable (either no row or data_unavailable=True).
        Raises RuntimeError on database errors or data type mismatches.

        VALIDATION RULES:
        - Row length validation: Must have 15 columns (pe_ratio, pb_ratio, ps_ratio, peg_ratio,
          dividend_yield, fcf_yield, forward_pe, ev_ebitda, ev_revenue, margin_of_safety_pct,
          market_cap, net_payout_yield, pe_ratio_unavailable_reason,
          forward_pe_unavailable_reason, data_unavailable) - the two *_unavailable_reason
          columns were added 2026-08-28 to distinguish "genuinely missing data" from
          "unprofitable company / negative earnings forecast" for P/E and Forward P/E (see
          _score_value's "UNPROFITABLE-COMPANY FLOOR ADDED 2026-08-28" docstring note).
        - Schema mismatch (len(row) < 15) → raises ValueError immediately
        - All numeric fields converted via safe_float() (detects data corruption)
        - data_unavailable=True flag → returns marker dict even if row exists
        - No row at all → returns marker dict with reason="no_value_metrics_found"

        CRITICAL FIX 2026-07-01: Now checks data_unavailable flag. Some securities have rows
        marked data_unavailable=True with NULL values. Previously returned NULLs instead of
        marker; now properly returns marker dict.

        MINIMUM DATA REQUIREMENT: Row must have exactly 7 columns. Missing columns causes immediate
        fail-fast ValueError. Required metric for stock scoring (critical upstream loader).
        """
        row = self._value_cache.get(symbol)
        if row:
            # CRITICAL: Validate row has expected 15 columns before accessing indices
            # (11 + market_cap added 2026-08-25 to close the Size-factor gap, +1 more
            # net_payout_yield added 2026-08-26, +2 more pe_ratio_unavailable_reason/
            # forward_pe_unavailable_reason added 2026-08-28 - see _score_value's docstring)
            if len(row) < 15:
                raise ValueError(
                    f"[STOCK_SCORES] {symbol}: value_metrics row has {len(row)} columns, expected 15. "
                    f"Schema mismatch detected - cannot safely access data. Failing fast."
                )
            data_unavailable = row[14]
            # If marked unavailable, return marker even if row exists
            if data_unavailable:
                logger.debug(
                    f"[LOAD_STOCK_SCORES] {symbol} marked data_unavailable in value_metrics "
                    f"(likely security with missing pricing data)"
                )
                return {"symbol": symbol, "data_unavailable": True, "reason": "value_data_marked_unavailable"}
            # Row exists and data is available
            return {
                "pe_ratio": safe_float(row[0], f"{symbol}.pe_ratio"),
                "pb_ratio": safe_float(row[1], f"{symbol}.pb_ratio"),
                "ps_ratio": safe_float(row[2], f"{symbol}.ps_ratio"),
                "peg_ratio": safe_float(row[3], f"{symbol}.peg_ratio"),
                "dividend_yield": safe_float(row[4], f"{symbol}.dividend_yield"),
                "fcf_yield": safe_float(row[5], f"{symbol}.fcf_yield"),
                "forward_pe": safe_float(row[6], f"{symbol}.forward_pe", allow_none=True),
                "ev_ebitda": safe_float(row[7], f"{symbol}.ev_ebitda", allow_none=True),
                "ev_revenue": safe_float(row[8], f"{symbol}.ev_revenue", allow_none=True),
                "margin_of_safety_pct": safe_float(row[9], f"{symbol}.margin_of_safety_pct", allow_none=True),
                "market_cap": safe_float(row[10], f"{symbol}.market_cap", allow_none=True),
                "net_payout_yield": safe_float(row[11], f"{symbol}.net_payout_yield", allow_none=True),
                "pe_ratio_unavailable_reason": row[12],
                "forward_pe_unavailable_reason": row[13],
            }
        # No row exists at all
        logger.warning(
            f"[LOAD_STOCK_SCORES] No value metrics available for {symbol} - score completeness will be reduced"
        )
        return {"symbol": symbol, "data_unavailable": True, "reason": "no_value_metrics_found"}

    def _get_stability_metrics(self, cur: Any, symbol: str) -> dict[str, Any]:
        """Fetch stability metrics for symbol.

        Returns explicit marker dict if data is unavailable (either no row or data_unavailable=True).
        Raises RuntimeError on database errors or data type mismatches.

        VALIDATION RULES:
        - Row length validation: Must have 9 columns (volatility_252d, volatility_60d,
          volatility_30d, beta, downside_volatility_252d/60d/30d, max_drawdown_1y,
          data_unavailable)
        - Schema mismatch (len(row) < 9) → raises ValueError immediately
        - All numeric fields converted via safe_float() (detects data corruption)
        - data_unavailable=True flag → returns marker dict even if row exists
        - No row at all → returns marker dict with reason="no_stability_metrics_found"

        CRITICAL FIX 2026-07-01: Now checks data_unavailable flag. Some securities have rows
        marked data_unavailable=True with NULL values. Previously returned NULLs instead of
        marker; now properly returns marker dict.

        CRITICAL FIX 2026-07-03: Now uses safe_float() for all numeric fields to detect
        data corruption. Previous inline float() bypassed error handling.

        FIX 2026-08-16: downside_volatility_60d/30d now included (columns already existed on
        stability_metrics, just never selected - see the cache-building query's comment).

        CLEANUP 2026-08-16 (later): debt_to_assets/debt_to_equity/current_ratio/quick_ratio/
        cash_per_share (fundamental leverage/liquidity metrics) and revenue_concentration_hhi
        (business diversification) are no longer merged in here - stability is meant to track
        price-volatility/risk-of-loss character, not balance-sheet fundamentals. debt_to_assets
        is scored in Quality's base quality_score formula (see _score_quality); debt_to_equity
        was scored via Quality's _score_financial_stability adjustment until the 2026-08-26
        literature audit removed it as a redundant transform of debt_to_assets ("pick D/A or
        D/E, not both") and deleted that now-dead function; revenue_concentration_hhi was
        dropped from scoring entirely per user request (not a stability signal).

        MINIMUM DATA REQUIREMENT: Row must have exactly 9 columns. Missing columns causes immediate
        fail-fast ValueError. Required metric for stock scoring (critical upstream loader).
        """
        row = self._stability_cache.get(symbol)
        if row:
            # CRITICAL: Validate row has expected 9 columns before accessing indices
            if len(row) < 9:
                raise ValueError(
                    f"[STOCK_SCORES] {symbol}: stability_metrics row has {len(row)} columns, expected 9. "
                    f"Schema mismatch detected - cannot safely access data. Failing fast."
                )
            data_unavailable = row[8]
            # If marked unavailable, return marker even if row exists
            if data_unavailable:
                logger.debug(
                    f"[LOAD_STOCK_SCORES] {symbol} marked data_unavailable in stability_metrics "
                    f"(likely security with insufficient price history)"
                )
                return {"symbol": symbol, "data_unavailable": True, "reason": "stability_data_marked_unavailable"}
            # Row exists and data is available
            metrics = {
                "volatility_252d": safe_float(row[0], f"{symbol}.volatility_252d"),
                "volatility_60d": safe_float(row[1], f"{symbol}.volatility_60d"),
                "volatility_30d": safe_float(row[2], f"{symbol}.volatility_30d"),
                "beta": safe_float(row[3], f"{symbol}.beta"),
                "downside_volatility_252d": safe_float(row[4], f"{symbol}.downside_volatility_252d", allow_none=True),
                "downside_volatility_60d": safe_float(row[5], f"{symbol}.downside_volatility_60d", allow_none=True),
                "downside_volatility_30d": safe_float(row[6], f"{symbol}.downside_volatility_30d", allow_none=True),
                "max_drawdown_1y": safe_float(row[7], f"{symbol}.max_drawdown_1y", allow_none=True),
            }
            return metrics
        # No row exists at all
        logger.warning(
            f"[LOAD_STOCK_SCORES] No stability metrics available for {symbol} - score completeness will be reduced"
        )
        return {"symbol": symbol, "data_unavailable": True, "reason": "no_stability_metrics_found"}

    def _get_momentum_metrics(self, cur: Any, symbol: str) -> dict[str, Any]:
        """Fetch momentum/RS metrics for symbol from momentum_metrics table.

        CRITICAL FIX 2026-07-18: Now reads precomputed momentum values from momentum_metrics
        table (populated by load_risk_metrics_daily.py) instead of computing from scratch.
        This fixes the issue where stock_scores had all NULL momentum despite momentum_metrics
        being populated.

        momentum_metrics provides:
        - momentum_1m, momentum_3m, momentum_6m, momentum_12m (already calculated)
        - data_unavailable flag (True if loader failed)

        Also merges in the latest RSI(14)/MACD/SMA-positioning from technical_data_daily (via
        self._technical_cache). These are a separate, independently-available source, so a
        symbol without usable price-return momentum can still contribute an RSI/MACD/SMA-only
        momentum score, and vice versa.

        UNIFIED 2026-08-28 (goal: momentum/risk factor logic review): this method used to treat
        "no momentum_metrics row at all for this symbol" and "momentum_metrics row present but
        data_unavailable=True" as two DIFFERENT cases with opposite outcomes - the former (added
        Session 416, 2026-07-25, "CRITICAL: Remove 7 silent fallback violations") returned a hard
        data_unavailable marker even when RSI/MACD were available, citing GOVERNANCE.md's
        no-secondary-fallback rule ("RSI/MACD are oscillators... not price-return momentum...
        substituting creates false signal diversification"); the latter (added 2026-07-20, never
        revisited by the Session 416 audit) kept scoring RSI/MACD/SMA as a partial momentum score
        in the exact same real-world situation. Two branches, same underlying condition (no
        price-return momentum for this symbol), opposite treatment - purely because of which of
        two upstream code paths happened to produce it, not because of any real signal-quality
        difference. That reasoning doesn't actually hold under GOVERNANCE's own rule: RSI/MACD/
        SMA are not substituting FOR price-return momentum here - they carry their own dedicated,
        independent weight slots in _score_momentum (21%/16%/8% = 45% combined) that are already
        scored alongside price-return momentum whenever ALL of it is present, so their
        contribution when price-return momentum alone is missing isn't a proxy fallback, it's the
        same self-normalizing "score what's independently available, drop what's missing" pattern
        every other pillar in this file already uses (see _score_risk's own docstring for the
        same principle stated explicitly). GOVERNANCE's actual no-fallback example ("short-term
        momentum when long-term unavailable") describes swapping one proxy for a structurally
        similar metric within the SAME family, which this isn't.
        Verified empirically before unifying (live local DB, exclude_etfs=True universe matching
        what this loader actually processes): 5,102/5,102 real-stock-universe symbols already
        have a momentum_metrics row (0 hit the old "row absent" branch at all - it was live dead
        code for the current universe); 30/5,102 are row-present-but-data_unavailable (the only
        branch that ever actually fired). So today's live scores are unaffected by this change -
        it closes a latent inconsistency (a landmine if the momentum_metrics/stock_scores
        universes ever drift apart) rather than changing any symbol's current score. Both cases
        now go through one shared path below.

        Returns dict with momentum values (which may be None for individual timeframes if
        upstream loader failed to calculate them).
        """
        try:
            tech_row = self._technical_cache.get(symbol, None)
            rsi_14 = safe_float(tech_row[0], f"{symbol}.rsi_14", allow_none=True) if tech_row else None
            macd = safe_float(tech_row[1], f"{symbol}.macd", allow_none=True) if tech_row else None
            sma_50 = safe_float(tech_row[2], f"{symbol}.sma_50", allow_none=True) if tech_row else None
            sma_200 = safe_float(tech_row[3], f"{symbol}.sma_200", allow_none=True) if tech_row else None
            close = safe_float(tech_row[4], f"{symbol}.close", allow_none=True) if tech_row else None
            # Decimal fraction (0.05 = +5%), matching _score_momentum's ±10%-range-maps-to-0-100
            # formula - NOT the *100 percentage scale the scores API computes for display.
            price_vs_sma_50 = (close - sma_50) / sma_50 if close is not None and sma_50 else None
            price_vs_sma_200 = (close - sma_200) / sma_200 if close is not None and sma_200 else None

            row = self._momentum_cache.get(symbol, None)

            if row is not None:
                # momentum_metrics cache has 5 columns: momentum_1m, momentum_3m, momentum_6m, momentum_12m, data_unavailable
                if len(row) < 5:
                    raise ValueError(
                        f"[STOCK_SCORES] {symbol}: momentum cache returned {len(row)} columns, expected 5. "
                        f"Schema mismatch detected. Failing fast."
                    )

                momentum_1m = safe_float(row[0], f"{symbol}.momentum_1m", allow_none=True)
                momentum_3m = safe_float(row[1], f"{symbol}.momentum_3m", allow_none=True)
                momentum_6m = safe_float(row[2], f"{symbol}.momentum_6m", allow_none=True)
                momentum_12m = safe_float(row[3], f"{symbol}.momentum_12m", allow_none=True)
                price_momentum_unavailable = bool(row[4])
                no_row_reason = "momentum_metrics_loader_failed"
            else:
                # No momentum_metrics row at all for this symbol. Treated identically to
                # row-present-but-data_unavailable=True below (see UNIFIED 2026-08-28 docstring
                # note above) - both mean "no price-return momentum for this symbol", and RSI/
                # MACD/SMA are independently scored either way, not substituted in as a proxy.
                momentum_1m = momentum_3m = momentum_6m = momentum_12m = None
                price_momentum_unavailable = True
                no_row_reason = "no_momentum_data_available"

            if price_momentum_unavailable:
                if rsi_14 is None and macd is None and price_vs_sma_50 is None and price_vs_sma_200 is None:
                    logger.warning(
                        f"[LOAD_STOCK_SCORES] No momentum data available for {symbol} - "
                        f"neither price-return momentum nor RSI/MACD/SMA positioning is usable."
                    )
                    return {"symbol": symbol, "data_unavailable": True, "reason": no_row_reason}
                return {
                    "momentum_1m": None,
                    "momentum_3m": None,
                    "momentum_6m": None,
                    "momentum_12m": None,
                    "rsi_14": rsi_14,
                    "macd": macd,
                    "price_vs_sma_50": price_vs_sma_50,
                    "price_vs_sma_200": price_vs_sma_200,
                }

            return {
                "momentum_1m": momentum_1m,
                "momentum_3m": momentum_3m,
                "momentum_6m": momentum_6m,
                "momentum_12m": momentum_12m,
                "rsi_14": rsi_14,
                "macd": macd,
                "price_vs_sma_50": price_vs_sma_50,
                "price_vs_sma_200": price_vs_sma_200,
            }
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(f"Database operation failed fetching momentum metrics for {symbol}: {e}") from e

    def _score_quality(self, metrics: dict[str, Any] | None, symbol: str) -> float | dict[str, Any]:
        """Score quality metrics on 0-100 scale.

        CRITICAL: Uses only pre-computed quality_score (official model consensus). No fallback
        computation - if pre-computed score missing, returns explicit data_unavailable marker.
        For financial accuracy, missing scores are better than fabricated heuristics.

        REBUILT 2026-08-26, EXTENDED 2026-08-27 (Quality pillar exhaustive-input review,
        user-directed - supersedes this docstring's earlier "9-weighted-component cluster
        blend" description, which described the c568eccfe state, not the current one). The
        upstream quality_score (load_value_quality_growth_metrics.py) is now an 8-weighted-
        component blend, no clusters: ROA 18%, ROCE 18% (replaces ROIC - fixes ROIC's
        cash-netting coverage gap), Debt-to-Equity 18% (replaces Debt-to-Assets - tests
        stronger, t=3.12 vs 2.18), FCF Margin 15% (replaces Accruals Ratio - independent
        signal, corr=0.13), ROE 11%, Margin Volatility (3Y)/Asset Turnover/Gross Profitability
        ~7% each - renormalized over whichever are available for a given symbol, with a
        40-point minimum-available-weight floor out of a 101-point nominal total (below that,
        quality_score is None rather than a thin-sample extrapolation - see
        load_value_quality_growth_metrics.py's quality_components comment). Weights are set
        from both full-sample t-stat magnitude AND a half-split time-stability check, not raw
        t-stat alone.

        Interest Coverage/Payout Ratio REMOVED 2026-08-27: both were live at 5% each on
        nothing but legacy assumption - properly isolated FM re-testing (own dropna scope, not
        bundled with unrelated candidates) found neither ever approached significance
        (interest_coverage t=0.63/-0.12/0.87, payout_ratio t=0.53/0.68/0.06, full/1st-half/
        2nd-half). Gross Profitability (Novy-Marx 2013) was originally dropped the same day for
        the same reason (t=1.02) but that number came from a JOINT dropna across 7 unrelated
        candidate columns at once - isolated, it recovers to t=3.25/3.93/1.11, a real signal
        the biased test was hiding, the same failure mode later found to have also hidden
        Margin Volatility's signal and distorted Growth's eps/revenue 1y weights. Current Ratio
        was tested and excluded (no cross-sectional signal despite being a standard
        quality-investing checklist item) - that rejection used isolated methodology from the
        start and was re-confirmed, not reversed.

        Operating Margin Trend/Net Margin Trend/ROE Trend: relocated here from Growth
        2026-08-27 (per Piotroski/QMJ improvement-in-profitability placement), then REMOVED
        from scoring again the same day (user directive, live-observed "No data" on the
        StockDetail page). Unlike the Interest Coverage/Payout Ratio/Gross Profitability
        re-checks above, isolated re-testing did NOT recover a signal for any of these 3
        (t=0.55/0.08/-0.01 full-sample) - genuinely dead, not a joint-dropna casualty. Still
        computed/persisted (quality_metrics table), not scored. See
        load_value_quality_growth_metrics.py's quality_components comment for the fuller
        removal note on all of the above.

        Altman Z''-Score ADDED then REMOVED same day (2026-08-26, user directive) - not on new
        negative evidence, but a methodological objection: the literature frames Z''-Score as a
        discrete distress-triage classifier ("quick check of economic health; if it flags a
        problem, do more detailed analysis"), not a continuously-scaled input meant to be
        averaged into a magnitude-weighted composite - independently reinforcing what the data
        already flagged as this component's weakest point (its t=3.49 came from only 41 months
        and decayed hard within that short window, t=4.40->1.39 half-split). Removed from
        scoring first, then removed entirely (computation, persistence, API, frontend) on a
        2026-08-29 user directive that the raw value wasn't worth keeping for reference alone;
        where a distress-flag use belongs (if anywhere) is deliberately left open for later, not
        decided today.

        This REPLACES the previous "_enhance_quality_score" ±10-point bump layer entirely -
        every signal that layer used to bump on is now either a real weighted input in the
        base formula above, superseded by a literature-grounded replacement, or dropped as
        redundant. Splitting one quality signal across two differently-weighted functions in
        two different files was real architectural debt (user-flagged 2026-08-26) independent
        of the literature findings - collapsing to one function fixes both at once.
        _score_financial_stability/_score_dte removed as dead code (no other callers).
        """
        if not metrics or metrics.get("data_unavailable"):
            logger.warning(f"[STOCK_SCORES] Quality metrics unavailable for {symbol}")
            return {"symbol": symbol, "data_unavailable": True, "reason": "no_quality_metrics_data"}

        # CRITICAL: Require pre-computed quality_score. Do NOT fall back to dynamic computation -
        # that creates fabricated scores from heuristics. Missing quality_score indicates an
        # upstream issue (Phase 3 didn't run or metrics incomplete).
        if metrics.get("quality_score") is not None:
            quality_score_value = safe_float(metrics["quality_score"], f"{symbol}.quality_score")
            if quality_score_value is not None:
                logger.debug(f"[STOCK_SCORES] Using pre-computed quality_score for {symbol}: {quality_score_value}")
                return quality_score_value

        # FAIL-FAST: No pre-computed score and no fallback. This is explicit data unavailability.
        logger.warning(
            f"[STOCK_SCORES] Quality score unavailable for {symbol}. "
            f"Pre-computed quality_score missing - Phase 3 may not have completed or metrics incomplete. "
            f"Returning data_unavailable marker instead of fabricated heuristic score."
        )
        return {"symbol": symbol, "data_unavailable": True, "reason": "quality_score_unavailable"}

    def _score_growth(self, metrics: dict[str, Any] | None, symbol: str) -> float | dict[str, Any]:
        """Score growth metrics on 0-100 scale via a multi-input blend. Returns marker dict if
        no real data.

        RESTORED TO MULTI-INPUT 2026-08-28 (user directive, /goal session: "get the rest of the
        growth inputs back in there the ones that are in the react" + explicit pushback that
        revenue_growth_1y's sign-flip "shouldn't be inverted"). This pillar had been rebuilt 3
        times in 48h into an increasingly narrow single-input, sign-flipped design (the original
        11-input blend -> book_value_growth alone -> revenue_growth_1y alone, each justified by
        isolated Fama-MacBeth "winner take all" testing - see git history for that evidence
        trail, not repeated here since it no longer describes the live formula). A same-day
        re-test of a genuine multi-input blend (algo/research/growth_multi_input_blend_test_20260828.py)
        found neither the single-input nor an equal-weighted 5-candidate blend era-robust once
        controlled for the other 5 pillars (see
        growth_multi_input_blend_tested_not_robust_reit_signal_backwards_20260828 in memory) -
        so this restore is NOT an evidence-driven reversal, it's an explicit user override of
        that evidence, the same footing as this file's Dividend-Yield-over-Net-Payout-Yield
        precedent (_score_value's docstring: "REVERTED back to Dividend Yield 2026-08-28 on
        explicit user directive").

        Scores every growth field the frontend's Growth tab displays (GROWTH_SCHEMA in
        StockScoreAccordion.jsx / GROWTH_SCORE_FIELDS above) - the single-input design was
        starving large swings of the universe of any Growth score purely on whichever ONE field
        happened to be missing for a given symbol (e.g. book_value_growth's 72.9% coverage
        starving ~27% of the universe), and displaying a dozen "computed but unscored" fields
        next to a "sole input" weight badge made the tab actively misleading (looked
        multi-factor, wasn't). Equal-weighted average of whichever of the GROWTH_SCORE_FIELDS
        candidates are non-null for this symbol (partial-availability renormalization - the
        same "score what's available, drop what's missing, don't hand the drop-outs' weight to
        a different candidate" pattern _score_quality/_score_stability already use elsewhere in
        this file) - NOT sign-flipped, plain "higher growth = higher score" per the user's
        explicit direction, overriding this file's own prior growth-reversal research (Cooper/
        Gulen/Schill 2008) for every candidate below, not just revenue_growth_1y.

        quarterly_growth_momentum/earnings_growth_4q_avg are both computed by
        _compute_quarterly_metrics in load_value_quality_growth_metrics.py (the loader that
        runs in the local dev pipeline, not the AWS-only enhanced loader an earlier version of
        this docstring wrongly attributed them to) and mirrored onto BOTH growth_metrics and
        quality_metrics - _get_growth_metrics reads growth_metrics's own copy of each, so
        `metrics` already carries both by the time this method sees it, same as every other
        candidate.

        REVISED 2026-08-31 (industry-alignment review, see GROWTH_SCORE_FIELDS's own docstring
        for the full rationale/evidence): net_income_growth_yoy swapped out for
        forward_eps_growth_current_fy/forward_eps_growth_next_fy/forward_revenue_growth_next_fy.
        forward_eps_growth_current_fy/next_fy and
        forward_revenue_growth_next_fy arrive from _get_growth_metrics already converted from
        their raw-fraction DB storage to the same percentage-point scale every other candidate
        uses (see that method's _scale_fraction_to_pct helper) - _score_single_growth's cap=30
        curve would otherwise silently collapse them toward the 0%-growth midpoint.

        Margin/ROE trend fields (operating_margin_trend/net_margin_trend/roe_trend) remain in
        Quality (relocated there 2026-08-27, then removed from scoring entirely the same day
        on their own isolated re-test - see load_value_quality_growth_metrics.py's
        quality_components comment) - not a Growth input either way, and NOT in
        GROWTH_SCORE_FIELDS.

        eps_growth_stability ADDED 2026-08-31 (/goal session, explicit user directive), then
        REMOVED again later the same day (separate /goal session, "figure out what is right and
        best... based on finance best practices, not our previous conversations" - see
        GROWTH_SCORE_FIELDS's own docstring for the full rationale). It was a dispersion metric
        (population stddev of trailing-4Q YoY EPS growth rates, percentage points, always >=0,
        lower=more consistent) scored via a dedicated inverted piecewise curve
        (_score_eps_growth_stability, kept below but unused by this method now) rather than
        _score_single_growth - real, non-redundant signal, but an MSCI Quality-index component
        (earnings variability), not a named Growth-factor descriptor anywhere, so it didn't clear
        the same canon bar the other 12 fields are held to. fcf_growth_yoy was removed the same
        pass for a different reason - not canonical either, AND its own era-split predictive sign
        flips (H1 t=-2.09, H2 t=+2.45, live-reproduced) rather than just being weak.

        RETURN TYPES (STRICT):
        - >=GROWTH_MIN_FIELDS_AVAILABLE of GROWTH_SCORE_FIELDS available → returns float (0-100)
        - metrics marked data_unavailable=True → returns marker dict (never None)
        - metrics is None or missing → returns marker dict (never None)
        - 1..GROWTH_MIN_FIELDS_AVAILABLE-1 candidates available → returns marker dict with
          reason="insufficient_growth_inputs_thin_sample" (see that constant's own docstring -
          added 2026-08-31, a 1-2 field renormalization is thin-sample extrapolation, not an
          honest partial score, same principle Quality already applies to quality_score)
        - every GROWTH_SCORE_FIELDS candidate is None → returns marker dict with
          reason="no_growth_inputs_available"

        ERROR HANDLING:
        - Type conversion errors → RuntimeError (via _safe_float, in _get_growth_metrics)
        - Negative growth rates → valid scores (negative growth maps to 0-40 scale, positive to
          40-100, both continuous through 0 - see _score_single_growth)

        Internal function: caller (_compute_stock_score) explicitly handles marker dicts
        and uses them for growth metric computation.

        MINIMUM DATA REQUIREMENT: at least GROWTH_MIN_FIELDS_AVAILABLE of GROWTH_SCORE_FIELDS
        must be non-NULL (see that constant's own docstring for why).
        """
        if not metrics or metrics.get("data_unavailable"):
            reason = metrics.get("reason") if metrics else "metrics_is_none"
            logger.warning(
                f"[STOCK_SCORES] Growth metrics unavailable for {symbol}: {reason}. "
                f"ROOT CAUSE: Check upstream growth_metrics loader (depends on annual_income_statement/"
                f"annual_balance_sheet from SEC filings). Some stocks may lack recent annual filings "
                f"(IPOs, private equity, international)."
            )
            return {"symbol": symbol, "data_unavailable": True, "reason": "no_growth_metrics_data"}

        def _score_single_growth(val: float | None, cap: float) -> float | None:
            """Score a single growth rate capped at `cap`%.

            Continuous through val=0: negative growth maps [-50, 0] -> [0, 40], positive
            growth maps [0, cap] -> [40, 100]. Both branches meet at 40 for 0% growth, so a
            modest positive grower always outscores any decliner.
            """
            if val is None:
                return None
            if val <= 0:
                # Negative growth: map [-50, 0] → [0, 40]
                # FIXED 2026-08-27 (goal-mode data-coverage audit): max(0, ...)/min(100, ...)
                # with int literals return the literal Python int when the float argument
                # saturates past the boundary (e.g. min(100, 105.3) -> int 100, not 100.0).
                # is_real_score() downstream does isinstance(result, float), so any saturated
                # score silently failed that check and got discarded as "unknown_reason" -
                # affected 761/5194 symbols (every one with book_value_growth <= -30% or
                # >= +50%, both common), NOT a data gap. Use float literals so the boundary
                # case still returns a real float.
                return max(0.0, 40 + (val / 50) * 40)
            # Positive growth: map [0, cap] → [40, 100]
            return min(100.0, 40 + (val / cap) * 60)

        def _score_eps_growth_stability(val: float | None) -> float | None:
            """Score eps_growth_stability (population stddev, percentage points, of the
            trailing-4-quarter YoY EPS growth rates) as an inverted "earnings variability"
            input: lower dispersion = more consistent execution = higher score. Always >=0, so
            it needs its own curve rather than _score_single_growth's signed [-50,cap] shape.

            Piecewise-linear "badness" curve (100 minus it), same convention this codebase
            already uses for other dispersion/volatility metrics (see _margin_curve in
            load_value_quality_growth_metrics.py's quality scoring), re-scaled for this field's
            live distribution (verified directly against growth_metrics, not assumed):
            p25~=18, median~=53, p75~=156, p90~=404 percentage points of stddev. Anchors: 0
            stddev -> 100 (perfectly consistent), ~p25 -> 80, ~median -> ~59, ~p75 -> ~23,
            >=p90 -> 0. Breakpoints are domain judgment calibrated to the real distribution,
            not separately fit/backtested - same caveat this file already applies to its other
            fixed-cap curves (e.g. the cap=30 above).
            """
            if val is None:
                return None
            if val <= 0:
                return 100.0
            breakpoints = [(20.0, 20.0), (75.0, 55.0), (200.0, 90.0), (400.0, 100.0)]
            if val < breakpoints[0][0]:
                badness = (val / breakpoints[0][0]) * breakpoints[0][1]
            else:
                badness = breakpoints[-1][1]
                for (x0, y0), (x1, y1) in itertools.pairwise(breakpoints):
                    if val < x1:
                        badness = y0 + (val - x0) / (x1 - x0) * (y1 - y0)
                        break
            return max(0.0, 100.0 - badness)

        # Equal-weighted blend, NOT sign-flipped (see docstring - explicit user override of
        # this file's own growth-reversal research). Cap of 30% reused across every signed-rate
        # candidate: all of them share the same _cagr()/YoY-%-derived percentage-point scale
        # this file has always used that cap for (domain judgment, not separately fit per
        # field - same caveat already applied elsewhere in this file, e.g. asset_turnover,
        # gross_profitability, fcf_margin). No dispersion-metric candidate is scored here since
        # eps_growth_stability's removal 2026-08-31 (see GROWTH_SCORE_FIELDS's own docstring) -
        # _score_eps_growth_stability is kept, unused, in case a future Quality-pillar pass wants
        # this exact well-tested dispersion curve for an earnings-variability input there.
        component_scores = []
        for field in GROWTH_SCORE_FIELDS:
            raw = metrics.get(field)
            if raw is not None and raw > GROWTH_INPUT_IMPLAUSIBLE_PCT:
                # See GROWTH_INPUT_IMPLAUSIBLE_PCT's docstring: exclude rather than score at a
                # saturated 100 - an implausibly extreme rate isn't comparable "growth quality"
                # to a genuine strong grower even though both would otherwise map identically.
                continue
            score = _score_single_growth(raw, 30)
            if score is not None:
                component_scores.append(score)

        if len(component_scores) >= GROWTH_MIN_FIELDS_AVAILABLE:
            growth_score = sum(component_scores) / len(component_scores)
            logger.debug(
                f"[STOCK_SCORES] {symbol} growth_score computed: {growth_score:.2f} "
                f"({len(component_scores)}/{len(GROWTH_SCORE_FIELDS)} inputs available)"
            )
            return growth_score

        if component_scores:
            logger.info(
                f"[STOCK_SCORES] {symbol} growth_score withheld: only {len(component_scores)}/"
                f"{len(GROWTH_SCORE_FIELDS)} inputs available, below GROWTH_MIN_FIELDS_AVAILABLE="
                f"{GROWTH_MIN_FIELDS_AVAILABLE}. See that constant's docstring - a 1-2 field "
                f"renormalization is thin-sample extrapolation, not an honest partial score."
            )
            return {
                "symbol": symbol,
                "data_unavailable": True,
                "reason": "insufficient_growth_inputs_thin_sample",
            }

        logger.warning(
            f"[STOCK_SCORES] {symbol} growth_score computation FAILED: all {len(GROWTH_SCORE_FIELDS)} "
            f"growth candidates are None. ROOT CAUSE: growth_metrics row exists but no growth "
            f"field could be computed for this symbol."
        )
        return {"symbol": symbol, "data_unavailable": True, "reason": "no_growth_inputs_available"}

    def _score_value(self, metrics: dict[str, Any] | None, symbol: str) -> float | dict[str, Any]:
        """Score value metrics on 0-100 scale. Returns marker dict if no real data.

        ARCHITECTURE CHANGE 2026-08-28 (goal: "what does IBD/the best and brightest do" - see
        VALUE_RISK_INTERACTION_MAX_SHIFT's neighbor, update_value_multiples_percentiles()'s own
        docstring, for the full evidence trail and citations). P/E, P/B, and P/S are no longer
        genuinely scored by THIS function's fixed piecewise curves (`_pe_curve_score`/
        `_pb_curve_score`/`_ps_curve_score`) - those now only provide a PROVISIONAL Pass-1
        placeholder. The real score is a cross-sectional PERCENTILE RANK against the current
        run's universe, computed in `update_value_multiples_percentiles()` (post_run(), a batch
        pass that overwrites value_score/composite_score after every symbol has been scored) -
        the same two-phase provisional-then-corrected pattern this file's `update_rs_percentiles()`
        already established for Momentum's rs_percentile. Directly tested against 3 alternatives
        (live fixed curve / cross-sectional z-score / 5yr-own-history time-series / a hybrid of
        the last two, matching MSCI's own published methodology) via
        algo/research/value_absolute_curve_vs_relative_ranking_20260828.py: cross-sectional
        percentile beat the fixed curve in EVERY era and spec tested (full-sample multivariate
        t=0.98 -> 2.02, ERA1 -0.75 -> 0.12, ERA2 2.48 -> 3.06; univariate 2.06 -> 3.29, 0.57 ->
        1.38, 2.55 -> 3.48) - a consistent, monotonic improvement, not a single lucky window.
        Time-series/hybrid did NOT help on this data (flat-to-negative, t=-0.44 to -0.10) despite
        MSCI's own published finding that combining both helps in their broader dataset - not
        implemented here since it doesn't hold on THIS repo's actual history. PEG/FCF/dividend/
        margin_of_safety are UNCHANGED by this - only PE/PB/PS's construction method changed,
        not their weights at the time (12/30/27) or the other 4 inputs. PB/PS's own weights
        (now 33/29) and the PEG trim / Forward P/E addition below are LATER, separate changes -
        see "PEG - TRIMMED FURTHER, NOT REMOVED" and "FCF YIELD - RESOLVED 2026-08-28" notes.

        Uses weighted scoring (2026-09-01, FINAL/CURRENT): P/E (27%) + P/B (27%) + P/S (27%)
        + Forward P/E (9%) + Dividend Yield (10%) - five scored inputs, no PEG, no Margin of
        Safety. EQUAL-WEIGHTED the 3 core multiples this session (user directive: "lets get the
        weightings more normal the 41% still seems wacky... is that what the industry players
        set these at too?") - the prior 12/41/35 split was DATA-DRIVEN (whichever multiple
        backtested strongest on this repo's own sample got more weight, 3 separate times), not
        matched to how real multi-metric Value composites are actually built (Fama-French's
        classic HML uses book-to-market alone; AQR/practitioner composites average their core
        ratios roughly equally). Forward P/E and Dividend Yield stay smaller satellite weights
        (9%/10%) rather than equal to the 3 core multiples - thinner history and weaker
        evidence respectively, not "core" descriptors in the cited methodologies either. Every
        earlier weight (12/39/34/4/11, then 12/41/35/4/8) quoted throughout the rest of this
        docstring is superseded by this line wherever they conflict.
        This is the end state of a same-day, goal-driven ("is this value score right per
        industry best practice") full re-audit against how real systematic Value factors are
        actually built (MSCI Enhanced Value/World Value, Russell, S&P Style, Barra,
        Fama-French/AQR) - see the dated notes below for each removal's full reasoning:
          - FCF yield REMOVED (robustly wrong-signed, independently re-verified three separate
            times - see "FCF YIELD - RESOLVED 2026-08-28" below).
          - PEG REMOVED ENTIRELY (later than FCF - a first pass only trimmed it 7%->3%, see
            "PEG - TRIMMED FURTHER, NOT REMOVED"; REMOVED FOR GOOD this same day, later pass,
            once the question shifted from "is it statistically weak" to "does a growth-blended
            ratio belong in a Value factor at all" - no mainstream methodology includes one,
            and this repo's own 15-pair pillar-interaction sweep found Growth x Value isn't
            era-robust either (only Value x Risk is) - see "PEG - REMOVED FROM SCORING
            2026-08-28" below. Its 3% went to Dividend Yield, 8%->11%.
          - Margin of Safety / DCF discount to intrinsic value REMOVED (an intrinsic-value/
            deep-value screening tool by industry convention, not a systematic Value-factor
            input - see "MARGIN OF SAFETY - REMOVED FROM SCORING 2026-08-28" below). Its 11%
            went to P/B (+6) and P/S (+5).
          - P/E and Forward P/E: NOT removed, but FIXED - both were silently excluding
            unprofitable/negative-forecast companies (2283/2519 P/E NULLs, 848/1560 Forward P/E
            "no estimates" rows are actually this case, not missing data) instead of correctly
            scoring them low, the same selection-bias bug class this file's own PE-vs-PB/PS
            ranking dispute was already caught on once before - see "UNPROFITABLE-COMPANY
            FLOOR ADDED 2026-08-28" / "UNPROFITABLE-FORECAST FLOOR ADDED 2026-08-28" below.
        Pre-2026-08-28 weights (12/30/27/PEG 7/FCF 9/Div 8/MoS 7), and every later-superseded
        same-day state (PEG-fully-removed/ForwardPE-7%; 12/33/29/.../MoS 11%; 12/39/34/PEG
        3/FwdPE 4/Div 8/MoS 11), are ALL STALE if seen anywhere - this docstring's weighted
        scoring line above is the only current one.
        Net Payout Yield (dividends + buybacks) REPLACED Dividend Yield 2026-08-26 on stronger
        multivariate evidence (t=3.05 vs. dividend_yield's own t=1.55-2.28 - see "FULL VALUE
        PILLAR RE-AUDIT" note below), then REVERTED back to Dividend Yield 2026-08-28 on
        explicit user directive ("we want the dividend yield instead of that payout shit") -
        an evidence-override-by-user-judgment case, same precedent as this file's Amihud/Size
        history. net_payout_yield stays fetched/computed (value_metrics.net_payout_yield) but
        is no longer scored here. Amihud illiquidity REMOVED 2026-08-26 (added, then removed,
        same day - see that same note for why a genuinely-validated signal was still taken out).
        PE/PB/PS/FCF reweighted 2026-08-25 (see "PE-vs-PB/PS RANKING - REVERSED" note below)
        after a selection-bias fix reversed which of the three multiples is strongest.
        EV/EBITDA and EV/Revenue REMOVED 2026-08-25 (see RESOLVED note below) - duplicated
        P/E and P/S respectively, not independent signals. PE/PB/PS weighting has moved
        several times the same day and once more the day after on a corrected sample - see
        "PE-vs-PB/PS RANKING - REVERSED" note below for the ranking (PB strongest, PS second,
        PE weakest) before trusting any earlier note in this docstring's own history. Peak
        zone for growth stocks: P/E 15-30, P/B < 5, PEG < 1-2, positive FCF yield, positive
        margin of safety.

        SIZE FACTOR added 2026-08-25 as a 20%-weighted sub-component (market cap, Fama-French
        SMB / Banz 1981), tested at t=-5.37 standalone. PROMOTED to its own top-level 7th
        pillar 2026-08-26 (see StockScoresLoader._score_size and _compute_stock_score's "SIZE
        PROMOTED TO 7TH PILLAR" docstring section for the full evidence trail: size_proxy
        t=7.63 multivariate, more than 3x every other pillar's own coefficient) - REMOVED from
        this function entirely to avoid double-counting now that it has its own composite
        slot. The 7 remaining inputs above were rescaled back to their pre-Size-addition
        relative proportions (each x1.25, restoring the 100% they held before Size's 20%
        carve-out) rather than left permanently discounted for an input that no longer lives
        here. SUPERSEDED the same day by the "AMIHUD ILLIQUIDITY" note below - those same 7
        inputs were rescaled again (x0.92) a few hours later to free 8 points for the new
        Amihud sub-component, so the live weights in the code above no longer match the x1.25
        figures quoted here; this paragraph is kept for history, not current state.

        REDESIGNED 2026-08-25 (goal: full scoring-architecture audit): PE was 45% (more than
        double every other input) despite being the empirically WEAKER of the three
        traditional value multiples in our own forward-1y-return panel (PE Spearman=-0.091,
        PB=-0.137, PS=-0.146, n=9.2k/12.2k/12.3k) - consistent with the literature (Fama-French
        value work has centered on book-to-market, not P/E, since the 1990s). Shifted weight
        toward PB/PS accordingly. Forward P/E removed entirely: analyst_earnings_estimates has
        zero historical depth (all rows fall within a single 3-week window), so it cannot be
        tested, and it shares trailing P/E's weaker theoretical standing plus adds analyst-
        forecast optimism bias on top. Dividend yield cut to a token weight (not removed) -
        tested inconclusive in our data (marginal p=0.036 full-sample, and the effect vanished
        entirely - p=0.542 - in the best-covered 2019-2024 sub-period), so there's no basis to
        trust either direction at material weight. Margin-of-safety's weight reduced (not
        removed) to reflect its already-documented DCF growth-cap bias above, without
        discarding a component with real, if imperfect, information content. A head-to-head
        composite backtest (old weights vs. these new weights, same panel, same forward-return
        target) showed the new mix modestly but genuinely outperforming: Spearman 0.150 vs.
        0.142, p=6.2e-70 vs. 1.6e-62, top-minus-bottom quintile spread 19.84 vs. 18.22 points.
        Caveat: that backtest, like every price-return test in this file's recent history, only
        has real price coverage from ~2020 onward - it validates the reweight within that
        window, not across market cycles the data can't reach. CORRECTION 2026-08-25 (later
        pass): the "10 of 10,982 symbols pre-2020" claim above doesn't hold up - direct query
        (`SELECT date_trunc('year',date), COUNT(DISTINCT symbol) FROM price_daily GROUP BY 1`)
        shows 3,497 distinct symbols with 2019 coverage and real (if thinner) coverage back to
        1962 (29 symbols) - growing roughly monotonically to 10,982 by 2025. The "~2020 onward"
        framing may still be directionally fine (breadth roughly doubles 2020-2021, from 3,730
        to 6,591 symbols), but the specific "10 symbols" number was wrong; left uncorrected
        elsewhere until now because it wasn't blocking anything, but flagging since
        algo/research/fama_macbeth_*.py's tests now use the fuller history.

        REINSTATED 2026-08-24 (user-directed, goal: NVDA margin-of-safety audit): removed
        2026-08-18 (commit e38a6667d) on the reasoning that margin_of_safety_pct should stay
        display-only for cross-symbol comparability. User explicitly asked for it back in the
        Value calculation - restored verbatim (same curve/weight as the original 2026-08-17
        add, commit 28e7ebf7d). Known caveat carried over from the DCF audit the same day: the
        underlying DCF caps forecast growth at 15%/yr, so a hypergrowth name (priced for far
        higher growth than the cap) will structurally show a large negative margin of safety
        here even when its other fundamentals are excellent - this is a real, understood bias
        in this specific input, not a bug in the scoring math.

        OPEN QUESTION flagged 2026-08-25 (same day, later pass - goal: re-audit ALL stock_scores
        inputs without bias toward what already shipped). Built
        algo/research/fama_macbeth_value_factors.py - point-in-time P/E, P/B, P/S, FCF yield,
        dividend yield, EV/EBITDA, EV/Revenue from annual_income_statement/annual_balance_sheet/
        annual_cash_flow (PEG and margin-of-safety out of scope - PEG needs a growth cross-term,
        margin-of-safety is a full DCF model, not a single ratio). Two findings:
        (1) Univariate Fama-MacBeth ranks PE (t=-3.70) at least as strong as PB (t=-2.35) and PS
        (t=-2.97), the OPPOSITE ranking from this docstring's own pooled-Spearman claim above
        (PE=-0.091 weakest, PB/PS=-0.137/-0.146 strongest) that justified cutting PE's weight
        from 45% to 18% - not yet reconciled, same tier of open question as Growth's
        eps_growth_1y/asset_growth_yoy finding. (2) Measured directly (150-month pooled
        correlation, n=45,806): ps and ev_revenue are LITERALLY the same signal (r=1.00 - EV
        only adds net debt/share, negligible next to price for most names), and pe/ev_ebitda are
        near-duplicates (r=0.93) - the identical "counted twice" bug class already caught and
        fixed for Momentum's ROC-vs-return-windows redundancy in the 92cd092ce redesign, just
        not caught here: live weights P/S 18% + EV/Revenue 8% put 26% combined weight on ONE
        signal, P/E 18% + EV/EBITDA 8% put 26% on another. pb is the most genuinely distinct
        multiple (only 0.32-0.38 correlated with pe/ps/ev_ebitda/ev_revenue); fcf_yield and
        dividend_yield are both essentially uncorrelated (~0.00) with the multiples and each
        other - real diversifying signals, not redundant ones (fcf_yield t=1.62 positive,
        directionally right but not quite significant; dividend_yield t=0.98, consistent with
        this docstring's own earlier "inconclusive" finding).

        RESOLVED 2026-08-25 (same-day follow-up): acted on the duplicate-signal finding, but
        NOT on the separate, still-unreconciled PE-ranking dispute above (pooled Spearman ranks
        PE weakest; univariate FM ranks it strongest) - the duplicate collapse is independent of
        that dispute and doesn't require resolving it first, unlike a full PE/PB/PS reweight
        would. ev_ebitda and ev_revenue removed entirely from scoring (still fetched/displayed -
        same "computed but unused by scoring" treatment as other removed-from-scoring fields
        elsewhere in this file) since r=1.00/0.93 means they added no information P/S and P/E
        didn't already carry. The freed 16pts went to the three inputs this same pass identified
        as genuinely distinct/diversifying rather than split proportionally: PB (+6, "the most
        genuinely distinct multiple" per the correlation evidence above - deliberately NOT
        boosted using the disputed PE-vs-PB/PS ranking, only using the separate distinctness
        finding), FCF yield (+6, t=1.62, real near-uncorrelated diversifier, directionally
        significant-adjacent), Dividend yield (+2) and Margin of Safety (+2, both real if
        weaker/untested-here diversifiers - DCF-based MoS wasn't in this FM panel's scope, see
        the panel's own docstring). PE/PS themselves left untouched precisely because their
        correct relative weighting is the open, unreconciled question - this pass fixes the
        unambiguous redundancy without pre-judging that separate dispute.

        PE-vs-PB/PS RANKING DISPUTE - RESOLVED 2026-08-25 (same-day follow-up, sub-period
        robustness check, same method that closed Stability's max_drawdown_1y and Momentum's
        RSI questions this session): unlike those two, which turned out to be fragile/decaying
        under the same check, this one is genuinely robust. Ran two independent FM tests
        (the original univariate run above, and a fresh full re-run with a wider 2014-2026
        window): BOTH find all three multiples negatively signed and strongly significant in
        EVERY sub-period tested - full sample, first/second half, and all three terciles, no
        exceptions, no sign flips, no fading (fresh run: PE t=-4.93/-2.44/-4.37 half-split,
        PB t=-4.39/-1.75/-4.21, PS t=-5.13/-3.53/-3.88 - all comfortably significant even in
        the weakest sub-period). Critically, PB is the CONSISTENTLY WEAKEST of the three in
        both runs (not the strongest, as the original pooled-Spearman claim asserted), and PE
        is comparably strong to PS in both runs (not uniquely weak, as that same claim
        asserted and used to justify cutting PE 45%->18%). The original pooled-Spearman
        ranking was very likely a methodology artifact, not a real cross-sectional pattern:
        it used value_metrics' CURRENT-SNAPSHOT ratios (no history - see this file's own
        repeated caveat that value_metrics/growth_metrics/etc. are single-row-per-symbol
        snapshots) joined against a pooled panel of historical forward returns, which is not
        point-in-time correct and pools non-independent symbol-months exactly the way this
        file's other FM-vs-pooled-Spearman comparisons (Growth, Momentum, Stability) already
        established overstates/misstates significance - this is the same methodology-quality
        gap, just discovered later for Value specifically. ACTED ON: PE 18%->22%, PB 26%->18%,
        PS 18%->22% (PE/PS raised to reflect being robustly comparable-to-strongest rather
        than PE being uniquely weak; PB lowered to reflect being robustly weakest, though
        still real and significant - not cut to zero). Combined PE+PB+PS weight held at 62%,
        unchanged from the post-duplicate-collapse total above - this redistributes within
        the three multiples, it doesn't reopen the EV/EBITDA/EV/Revenue redistribution.

        INDEPENDENT RE-VERIFICATION 2026-08-25 (goal: dig in and be certain before acting
        further, not just trust an existing docstring claim). The "no exceptions, no sign
        flips, no fading" characterization above did not reproduce when independently re-run
        from scratch with the same script (algo/research/fama_macbeth_value_factors.py,
        same 2014-2026 window, same half/tercile split logic): first-half t-stats came back
        PE=-1.80, PB=+0.22 (wrong-signed), PS=-0.08 (near zero) - materially weaker than the
        PE=-4.93/PB=-4.39/PS=-5.13 claimed above, not a rounding difference. Second half and
        full-sample numbers DID reproduce closely (full sample PE=-3.70/PB=-2.35/PS=-2.97,
        matching this docstring's own OPEN QUESTION section above almost exactly). Most
        likely explanation: the pre-2020 sample is known-thin (this docstring's own
        CORRECTION note above: real but much sparser symbol coverage before ~2020, breadth
        roughly doubling 2020-2021), so first-half FM estimates are noisier and more
        sensitive to exact universe/date-boundary choices than a single re-run assumed -
        flagging as a real source of estimation uncertainty rather than treating either run's
        first-half numbers as precise. What DOES hold up across every check, both runs: PB is
        the consistently weakest of the three (worst-or-tied in every sub-period tried,
        including outright wrong-signed in the noisiest one) - the one part of the original
        claim that's robust to independent reproduction. PE-vs-PS is NOT reliably
        differentiable though (flips which is stronger across sub-periods in the fresh run) -
        so PE/PS are kept equal to each other (not one raised over the other) rather than
        the original claim's implicit "both robustly strong" framing. ACTED ON (modest,
        proportionate to what's actually robust): PB cut a further 14%->10%, freed 4pts split
        evenly to PE/PS (18%->20% each) - a small additional adjustment reflecting the
        strengthened (if less precisely quantified) case that PB is weak, not a large move on
        an uncertain number. Combined PE+PB+PS still 50% (post-Size-scaling total), unchanged.

        PE-vs-PB/PS RANKING - REVERSED 2026-08-25 (later same day, follow-up to
        [[composite_weights_reweighted_size_factor_reconfirmed_20260825]]'s top-level pass,
        which flagged Value's own internal weighting as a possible efficiency problem worth a
        dedicated look). Every prior pass above - including both "independent
        re-verifications" - tested via algo/research/fama_macbeth_value_factors.py's ORIGINAL
        design: a strict dropna() requiring ALL SIX value inputs (PE/PB/PS/FCF/dividend/EV
        fields) simultaneously non-null every symbol-month. Requiring PE specifically means
        requiring POSITIVE EARNINGS (PE is only computed for eps>0) - which systematically
        excludes unprofitable/distressed companies, exactly the population smaller-cap and
        deep-value effects concentrate in. This is the identical selection-bias mechanism the
        top-level composite test's own redesign just diagnosed and fixed (see that memory) -
        just never applied back to this pillar's own internal component test.

        Redesigned this script's sample the same way (only forward return mandatory; each
        input z-scored over whatever's available that month, missing imputed to 0) and reran:
        median cross-section jumped 1,285->2,604 symbols. Result completely inverts the
        standing "PB is weakest" conclusion: pooled multivariate PB t=-6.06 (vs PE t=-1.18,
        PS t=-4.01), pooled univariate PB t=-9.34 (vs PE t=-4.11, PS t=-7.33) - PB is now the
        STRONGEST of the three, PE the weakest (barely distinguishable from zero once
        controlling for the others). Sub-period-checked the same way the original ranking
        claim was (half-split, 2014-2020 vs 2020-2026): PB t=-2.41/-6.05, PS t=-2.41/-3.20,
        both robust in every half; PE t=+0.38/-1.78, not even consistently signed - the
        opposite robustness pattern from what justified the two prior PE/PB/PS reweights.
        Also re-tested Size (see the pillar's own docstring) in this same redesigned sample:
        t=-3.74 multivariate/-5.31 univariate pooled, t=-2.93/-2.55 sub-periods - confirms
        Size's already-live 20% weight was correctly calibrated, unaffected by this dispute.
        FCF yield flipped sign versus the strict-sample test (was t=+1.62 positive; redesigned
        sample gives t=-1.75 multivariate/-1.71 univariate pooled, negative in both
        sub-periods too) - genuinely sample-construction-sensitive, not a confident signal
        either direction, treated as a fragile null rather than acted on strongly either way.

        ACTED ON: PE 20%->10% (weak/inconsistent once controlling for the others - the
        opposite of its previous "robustly comparable-to-strongest" status), PB 10%->22%
        (robust strongest across univariate/multivariate/both sub-periods - the opposite of
        its previous "consistently weakest" status), PS 20%->21% (robust, modest bump),
        FCF yield 13%->10% (sign-unstable across sample constructions, trimmed for genuine
        uncertainty rather than a directional claim), dividend yield/Size/PEG/margin-of-safety
        unchanged. This is a full reversal of the PE/PB ranking specifically, not a refinement
        of it - the prior conclusion was built entirely on a methodology now shown to
        mechanistically exclude the population (unprofitable/small/distressed firms) where
        these effects concentrate. Both the old and new rankings can't be right; the new one
        is the one built on a sample that doesn't structurally exclude where the signal lives,
        and it reproduces across two independent specs (univariate/multivariate) and two
        independent sub-periods, the same bar the prior "independently re-verified" pass used.

        CONCURRENT INDEPENDENT VERIFICATION (merge note): a parallel session reached this same
        conclusion at nearly the same time via a near-identical redesign of
        algo/research/fama_macbeth_value_factors.py itself (rather than an ad hoc script),
        acting on the identical weight numbers (PE 10%/PB 22%/PS 21%/FCF 10%). Its multivariate
        PS coefficient came out weaker (t=-1.61 vs this pass's t=-4.01) because its
        VALUE_FACTOR_COLS still included ev_ebitda/ev_revenue (r=0.93/1.00 duplicates of pe/ps
        - see the RESOLVED note above) alongside PB/PS, reintroducing collinearity this pass's
        VALUE_FACTOR_COLS avoids by excluding those already-confirmed-dead columns entirely.
        PB's dominance (t=-5.93 to -9.34 depending on spec, both passes) is the load-bearing,
        convergent result either way.

        FULL VALUE PILLAR RE-AUDIT 2026-08-26 (goal: same rigor as the Quality pillar's re-audit
        - don't just accept the inherited PE/PB/PS/PEG/FCF/Div/MoS/Amihud list, re-derive the
        best inputs/weights from literature + our own validation). User flagged two specific
        doubts up front: whether Amihud illiquidity belongs in Value at all, and whether DCF
        margin of safety double-counts the other multiples. Extended
        algo/research/fama_macbeth_value_factors.py (previously only tested PE/PB/PS/FCF/Div/
        EV pairs) to close its two long-standing "out of scope" gaps - PEG (now computed via a
        reconstructed eps_growth_pct) and margin of safety (now computed via a vectorized
        replication of load_sec_valuations.py's real two-stage FCFE DCF, same growth-fade/
        terminal-value math, flagged known simplifications: flat 9.5% discount rate instead of
        per-symbol CAPM beta, and an unrefined fcf_base instead of production's OCF-CapEx-SBC+
        net-borrowing FCFE - see that script's docstring for the full reasoning) - plus merged
        in monthly Amihud illiquidity (reused from fama_macbeth_liquidity_factor.py) so the
        LIVE 8-input Value formula could be tested as ONE joint multivariate regression for the
        first time, not four separate ad hoc passes. Ran full-sample (2014-2026, 151 months) AND
        an independent half-split (2014-2020 / 2020-2026) robustness check, the same bar this
        docstring's own PE/PB/PS reversal was held to.

        AMIHUD ILLIQUIDITY - genuinely validated, removed anyway: multivariate t=2.99 full
        sample (controlling for PE/PB/PS/PEG/FCF/Div/MoS jointly), reproduces in BOTH
        sub-period halves (t=2.37 first half, t=1.91 second half) - a real, positive-signed,
        reproducible signal, NOT a fragile one-off. Also survives controlling for real
        point-in-time market cap directly (t=1.96, vs. the original validation's log-dollar-
        volume proxy) - pooled correlation with size is only -0.23, so this isn't just Size
        wearing a different name. Despite that, REMOVED from Value scoring: (1) literature
        consistently classifies Amihud/illiquidity as its OWN distinct risk factor family
        (Amihud 2002; Pastor-Stambaugh 2003; Acharya-Pedersen 2005's liquidity-adjusted CAPM),
        correlated with but conceptually separate from both size (SMB) and value (HML/
        book-to-market and other fundamentals-to-price ratios) in the standard multifactor
        literature - it measures trading friction, not cheapness relative to fundamentals, so
        folding it into "value_score" muddies what that score is supposed to mean even though
        the number itself is real. (2) User's own explicit read before any of this validation
        ran ("I don't think amihud belongs there") matches that literature classification
        exactly. (3) A memory record (size_pillar_removed_entirely_20260826, apparently from a
        different/not-yet-merged line of work - see the SIZE block's own note below, this
        branch still has _score_size live) describes the same reasoning being applied to Size:
        a well-replicated internal finding (there, size_proxy t=7.63) is not on its own
        sufficient justification for what belongs in this live-money system's scoring when the
        user's own judgment about pillar identity/interpretability says otherwise. Cited here as
        precedent for the REASONING, not as proof of what's currently live on this branch -
        and unlike that episode, this time the literature independently agrees rather than
        being silent. Amihud illiquidity stays computed and stored
        (technical_data_daily.amihud_illiquidity,
        migration 1232) for any future explicit ask - just not consumed here, same
        "computed-but-unscored" convention as ev_ebitda/ev_revenue above (forward_pe was in this
        same unscored bucket when this note was written - see "FORWARD P/E - ADDED 2026-08-28"
        docstring note above, it no longer is). Not re-homed to a new standalone "Liquidity"
        pillar either - that would repeat the exact
        8th-dimension-on-the-scores-page pattern the user already rejected for Size the same
        day; left for explicit future direction if ever wanted.

        MARGIN OF SAFETY - the "double counting" question, answered with evidence: pooled
        cross-sectional correlation with every other Value input is low (max |r|=0.21, with
        fcf_yield - sensible, both are cash-flow-based, but far from redundant; |r|<=0.12
        against pe/pb/ps/peg). NOT a duplicate signal by the same r=1.00/0.93 bar that killed
        EV/EBITDA and EV/Revenue in the RESOLVED note above. Predictive power: multivariate
        t=1.89 full sample (correctly signed - more undervalued by the DCF -> higher forward
        return), t=2.12 in the second (larger, more recent) half, but only t=0.30 in the first
        half - NOT robust across sub-periods by the strict bar the PE/PB/PS reversal was held
        to, most likely the same thin-pre-2020-sample noise already flagged elsewhere in this
        docstring, compounded here by the flat-discount-rate simplification (see the research
        script's docstring). Treated the same evidentiary tier as fcf_yield/dividend_yield
        already in this pillar (both also inconsistent across specs/sub-periods, both kept at
        modest weight rather than removed) - KEPT, weight reverted to its pre-Amihud-rescale
        7% rather than raised or cut further; the correlation evidence is the decisive answer to
        "is it double counting" (no), the predictive evidence is suggestive-but-not-conclusive
        (same as its neighbors), not a basis for a bigger move either direction.

        PEG - new finding, acted on: multivariate t=-0.73 full sample, and unlike margin of
        safety THIS one reproduces its weakness in both sub-period halves (t=-0.22 first half,
        t=-0.82 second half) despite a real, significant UNIVARIATE signal in both halves
        (t=-2.02, t=-2.73) - PEG's information is consistently subsumed once the other 7 inputs
        are already in the regression, a reproducible "loses its edge jointly" pattern distinct
        from (weaker than) the literal r=1.00/0.93 duplicates removed 2026-08-25, but real and
        replicated rather than a single-run artifact. Not eliminated outright (still a
        theoretically distinct, literature-grounded metric - PE adjusted for growth, Peter
        Lynch's heuristic - and its correlation with the other inputs is genuinely modest, e.g.
        r=0.13 with pe, r=-0.10 with margin_of_safety, nothing near duplicate territory) but
        trimmed 10%->7%, a modest, proportionate move matching this docstring's own established
        bar for acting on a reproduced-but-not-dramatic finding.

        PE/PB/PS - reconfirmed, not re-litigated: the fresh joint 8-input regression reproduces
        the existing "PE-vs-PB/PS RANKING - REVERSED" ranking exactly (PB strongest: t=-7.49
        full/-3.05/-7.64 halves; PS second: t=-4.40 full/-2.68/-3.52 halves; PE weakest: t=-1.59
        full/-0.27/-1.83 halves, barely distinguishable from zero in the first half) - this is
        independent re-verification via a materially different spec (5 more covariates: PEG,
        MoS, Amihud) landing on the identical rank order, real corroboration rather than a
        coincidence. PEG's 3pt trim redistributed to PB (+2) and PS (+1), proportionate to their
        now-doubly-confirmed relative strength, rather than split evenly or given to PE.

        FCF YIELD - escalated but NOT acted on this pass: multivariate coefficient is negative
        in ALL THREE windows tested (full t=-2.24, first half t=-0.52, second half t=-2.10) -
        i.e. controlling for the other inputs, a HIGHER fcf_yield predicts a LOWER forward
        return, the opposite of how this field is scored (higher yield = higher score). This is
        a more specific, more reproducible version of the "fragile, sample-construction-
        sensitive null" already flagged in the PE-vs-PB/PS RANKING - REVERSED note above -
        directionally consistent this time across all three windows, not flipping. Genuinely
        resembles the SIGNAL_QUALITY_SCORE volume_confirmation_score finding (a live input
        found significantly WRONG-SIGNED and excluded, see
        signal_quality_score_volume_confirmation_excluded_20260826) enough to flag prominently,
        but NOT acted on in this same pass: that finding was excluded only after being
        independently decomposed and reproduced across the full historical backtest, the same
        bar this docstring's own PE/PB/PS reversal needed two independent re-verifications
        before acting - one new spec's persistent sign here is a real, concerning signal to
        investigate next, not yet the same tier of evidence. Left at its current weight; flagged
        as the most likely next item if this pillar gets another pass.

        MISSING-INPUT CHECK 2026-08-26 (later same day, follow-up to the FULL VALUE PILLAR
        RE-AUDIT above - user asked explicitly: "are we missing any value input the literature
        would call for, or do we have them all?"). Checked two literature-established
        candidates neither previously computed nor scored anywhere in this system, via
        algo/research/fama_macbeth_value_factors.py's new CANDIDATE_COLS test (full sample +
        implicitly consistent with the rest of this pass's methodology):

        - net_payout_yield ((dividends+buybacks)/market cap, "total payout yield" -
          Boudoukh/Michaely/Richardson/Roberts 2007; O'Shaughnessy's "Shareholder Yield"):
          univariate t=3.27, multivariate t=3.05 jointly with the live 8 inputs - a real,
          robust, independent signal, stronger than dividend_yield's own t=1.55-2.28.
          ACTED ON: replaced dividend_yield in the weighted formula (see that field's own
          comment above for the full reasoning and the migration/loader wiring
          - migration 1236, load_sec_valuations.py, load_value_quality_growth_metrics.py).

        - ocf_yield (operating cash flow / price, O'Shaughnessy's price-to-cash-flow input,
          distinct from fcf_yield by not subtracting CapEx): univariate t=0.04 (no standalone
          signal) but multivariate t=2.12 once added alongside the live 8 - and adding it makes
          fcf_yield's own already-flagged wrong-signed coefficient WORSE (t=-2.24 -> t=-4.55),
          suggesting the CapEx-intensity DIFFERENCE between the two cash-flow measures is what
          actually carries information, not either one alone. NOT ACTED ON this pass - correctly
          untangling this needs resolving the FCF yield sign concern first (see that field's own
          docstring note above), not a clean single-input addition like net_payout_yield was;
          flagged as a follow-up to that same open item, not a separate one.

        FCF YIELD - RESOLVED 2026-08-28 (goal: "make sure we're using the right inputs the right
        way... aligned with industry standards and best practices"). The escalated-but-not-acted-
        on flag above needed a second independent re-verification before this file's own
        established bar (PE/PB/PS reversal, EV/EBITDA/EV/Revenue classification) would justify
        acting - re-ran algo/research/fama_macbeth_value_factors.py fresh (same script, fresh
        process, current live DB state) and independently split full/2014-2020/2020-2026:
        multivariate t=-2.43 full, -0.91 first half, -2.17 second half - reproduces the prior
        run's finding almost exactly (t=-2.24/-0.52/-2.10) and meets the bar: consistently
        negative-signed in every window, no flips, weaker only in the same thin-early-sample
        window every other reversal in this pillar is also weaker in. ACTED ON: fcf_yield REMOVED
        from scoring (see its own removal comment above). ocf_yield NOT added as a replacement
        despite the MISSING-INPUT CHECK note above finding it significant jointly (t=2.12-1.99) -
        its OWN univariate signal is null (t=0.04-0.08), meaning that jointly-significant number
        only holds while fcf_yield is ALSO in the regression (it's really measuring the CapEx-
        intensity spread between the two, not ocf_yield's own standalone information) - scoring
        ocf_yield alone once fcf_yield is gone would not reproduce that number and has no
        standalone basis. The CapEx-intensity-spread signal itself is real but stays an open
        research item, same conclusion the MISSING-INPUT CHECK note already reached, just no
        longer tangled with a live mis-signed field. Freed 9%: PB +3 (33%), PS +2 (29%), Margin
        of Safety +4 (11%) - the strongest existing multiples and the most distinct existing
        diversifier, not split proportionally, same reasoning precedent as EV/EBITDA/EV/Revenue's
        2026-08-25 freed weight.

        PEG - TRIMMED FURTHER, NOT REMOVED, 2026-08-28 (same goal as above). First pass this same
        day fully REMOVED PEG, reasoning it was both this pillar's weakest input by local
        evidence (t=-0.73 multivariate, subsumed once the other 7 are present) and absent from
        every mainstream institutional Value definition checked (Fama-French HML: book-to-market
        only; MSCI Value: book/price + forward earnings/price + dividend yield; S&P Style:
        book/earnings/sales-to-price; AQR value composites: book/earnings/forecast-earnings/
        sales/cash-flow-to-price - none use a growth-adjusted P/E). CORRECTED same day on user
        pushback ("why do you need to remove PEG? why not just leave it but keep it lower %") -
        the pushback is right: PEG's evidence tier is "weak but real, not a duplicate" (real
        univariate t=-2.02/-2.73 both sub-periods; r=0.13 with pe_ratio, r=-0.10 with
        margin_of_safety_pct - nowhere near the r=0.93/1.00 duplicate bar that justified removing
        ev_ebitda/ev_revenue, or the robustly-wrong-signed bar that justified removing
        fcf_yield). That's the SAME tier dividend_yield and margin_of_safety already sit at in
        this pillar (both kept at modest weight on similarly mixed evidence) - "absent from the
        big index providers' descriptor lists" doesn't distinguish PEG from margin_of_safety
        either (also absent from all four), which stayed on its own merits. Trimmed 7%->3%
        instead - real signal, modest weight, consistent treatment. The freed 4% went to Forward
        P/E below, not the full former 7% slot.

        FORWARD P/E - ADDED 2026-08-28 (user directive: "we want to use the forward PE... get
        this value score aligned with industry standards"). MSCI's Value index methodology uses
        12-month forward Earnings/Price as one of its three core descriptors (alongside book/
        price and dividend yield) - trailing P/E, which this pillar already scores, is exactly
        the input mainstream indices swap OUT in favor of this one. Explicitly a judgment-call
        inclusion, not an evidence-based one: analyst_earnings_estimates
        (load_analyst_earnings_estimates.py) has only ~22 trading days of real history as of this
        change (loader started ~2026-08-03) and there is no vendor source, free or otherwise,
        that exposes historical consensus estimates - yfinance's Ticker.earnings_estimate is a
        live-only snapshot, so this field is fundamentally unbacktestable today, not just
        untested, and will only become testable by letting daily collection accumulate over
        months. Same "user judgment overrides missing/thin local evidence" precedent already
        established for dividend_yield-vs-net_payout_yield and Amihud/Size. Implementation: joins
        the cross-sectional percentile-rank mechanism in `update_value_multiples_percentiles()`
        alongside P/E/P/B/P/S (see that method's docstring) rather than staying on a
        never-validated fixed curve - the same IBD/MSCI-style relative-ranking treatment already
        proven to beat fixed curves for the other three multiples in this exact system
        (algo/research/value_absolute_curve_vs_relative_ranking_20260828.py), extended here on
        the same logic. `_pe_curve_score` reused as-is for the Pass-1 provisional value (same
        conceptual ratio one year further out - no principled basis to invent different
        thresholds for data that's never been tested). Weight 4% - deliberately kept SMALLER
        than PEG's 3%-plus-real-evidence combination would otherwise suggest: forward P/E has
        real institutional standing but zero local evidence (unbacktestable, not just untested),
        so it shouldn't outweigh a field that has at least a real, if weak, statistical signal
        just because it inherited part of that field's old slot.

        EV/EBITDA AND EV/REVENUE - PILLAR CLASSIFICATION (not a re-add) 2026-08-28 (goal: "are
        EV/EBITDA and EV/Revenue really metrics that measure value as a factor? or do they
        really belong somewhere else?"). The RESOLVED note above answers "are they redundant
        WITHIN Value" (yes, r=0.93/1.00 vs PE/PS) but not "do they conceptually belong to Value
        at all" - built algo/research/ev_multiples_pillar_classification_20260828.py to answer
        that directly. Both are structurally PE/PS with one adjustment: EV = market_cap +
        total_debt - total_cash swapped in for market_cap (see load_sec_valuations.py's EV
        calc), so the real question is whether that net-debt wedge secretly belongs to a
        DIFFERENT existing pillar. Live cross-sectional check (n=2,203, sec_valuations join
        stock_scores): net_debt_ratio = (total_debt-total_cash)/market_cap is ~uncorrelated with
        risk_score (Spearman -0.001) - leverage risk is NOT hiding in Value under a value-multiple
        label, this system's Risk/Safety pillar doesn't already carry it. It IS meaningfully
        correlated with quality_score (-0.469), and the same holds isolating just the part of
        EV/Revenue that isn't PS (residual vs quality_score -0.454) - consistent with
        _score_quality already scoring debt_to_equity directly (see that method). CONCLUSION:
        EV/EBITDA and EV/Revenue ARE Value multiples by every standard classification (Damodaran
        relative valuation, AQR value composites - no literature treats them as Quality/Growth/
        Momentum/Risk/Size measures); the "belongs somewhere else" hypothesis doesn't hold for
        Risk specifically. But the incremental content they'd add beyond Value's own PE/PS is a
        leverage signal that already has a home in Quality's debt_to_equity, not a novel signal -
        so this REINFORCES the existing removed-from-scoring, still-computed-and-displayed
        treatment (same conclusion, sturdier reason: not just "duplicate of PE/PS" but "whatever
        isn't PE/PS is already Quality's job"), not a basis to move them to a different pillar or
        re-add them to Value. Side note, not reconciled: cross-sectionally PE/EV_EBITDA Spearman
        came back 0.69 here, well below the 0.93 the point-in-time panel found - PS/EV_Revenue
        reproduced closely (0.92 vs 1.00) - flagged as a live-snapshot-vs-panel discrepancy worth
        knowing about if EV/EBITDA's redundancy claim is ever leaned on again, not investigated
        further since it doesn't change this note's conclusion either way.

        No other candidate beyond these two was identified as both literature-established and
        not already covered by an existing input (P/E~Basu 1977 earnings yield, P/B~Fama-French
        HML, P/S~classic value screens, PEG~Lynch, FCF yield~practitioner cash-flow value,
        Margin of Safety~Graham/Buffett intrinsic value, Net Payout Yield~total payout
        literature - covers the standard "value composite" input families academics and
        practitioners actually use, e.g. AQR's HML-devil blend of B/P, E/P, S/P, forecast E/P).

        RETURN TYPES (STRICT):
        - metrics available with ≥1 value field → returns float (0-100)
        - metrics marked data_unavailable=True → returns marker dict (never None)
        - metrics is None or missing → returns marker dict (never None)
        - all value fields None → returns marker dict with reason="no_value_scores_computed"

        ERROR HANDLING:
        - Type conversion errors → RuntimeError (via _safe_float)
        - Negative P/E or P/B → skipped (invalid for valuation)

        Internal function: caller (_compute_stock_score) explicitly handles marker dicts
        and uses them for value metric computation.

        MINIMUM DATA REQUIREMENT: At least one of PE/PB/FCF/dividend metrics must be
        non-NULL. If all value metrics are None, returns data_unavailable marker.
        Critical metric for stock scoring (high priority upstream loader).
        """
        if not metrics or metrics.get("data_unavailable"):
            logger.warning(f"[STOCK_SCORES] Value metrics unavailable for {symbol}")
            logger.debug(f"[STOCK_SCORES] Returning data_unavailable marker for value_score({symbol})")
            return {"symbol": symbol, "data_unavailable": True, "reason": "no_value_metrics_data"}

        weighted_sum = 0.0
        total_weight = 0.0

        # P/E ratio: sweet spot 15-30 for growth momentum stocks
        # Weight 12% (reverted 2026-08-26 to its pre-Amihud-rescale value - Amihud removed
        # entirely from this pillar, see "FULL VALUE PILLAR RE-AUDIT" docstring note below).
        # Reconfirmed weakest of the three multiples in the fresh 8-input joint regression
        # (t=-1.59 full sample, -0.27/-1.83 sub-period halves) - see that note.
        # PE/PB/PS scoring: LIVE CROSS-SECTIONAL PERCENTILE, not a fixed absolute curve. This
        # per-symbol pass only knows THIS symbol's raw ratio, not the current run's universe
        # distribution, so it uses `_pe_curve_score`/`_pb_curve_score`/`_ps_curve_score` (the
        # OLD fixed-threshold formulas, preserved verbatim - see their own docstrings) as a
        # PROVISIONAL value here; `update_value_multiples_percentiles()` (post_run(), batch
        # pass, see its own docstring for the full evidence trail and the correction formula)
        # OVERWRITES value_score/composite_score with the true cross-sectional-percentile-based
        # multiples score once every symbol in this run has been scored. This two-phase
        # provisional-then-corrected pattern mirrors `update_rs_percentiles()`'s own established
        # precedent in this same file (Momentum's rs_percentile) - the only difference is that
        # here the correction feeds back into value_score/composite_score itself rather than a
        # separate auxiliary column, since PE/PB/PS are scored inputs, not just a display field.
        # UNPROFITABLE-COMPANY FLOOR ADDED 2026-08-28 (goal: "is this value score right per
        # industry best practice" - the P/E-vs-E/P gap). Institutional Value factors use
        # earnings YIELD (E/P), which stays well-defined and correctly negative for a
        # loss-making company; this file uses P/E (ratio form), which is mathematically
        # undefined for negative earnings and was previously just SKIPPED for those symbols -
        # renormalizing them onto P/B/P/S/etc. as if this component simply didn't exist,
        # rather than correctly scoring them low. Live-confirmed real scale: 2283 of 2519
        # universe pe_ratio NULLs (value_value_quality_growth_metrics.py's own audit) are
        # unprofitable companies with a real, present EPS <= 0, not missing data - the
        # `pe_ratio_unavailable_reason == "unprofitable_stock"` case below. Fix doesn't require
        # a new stored earnings-yield field: any negative earnings yield is, by definition,
        # worse than any non-negative one, so flooring at 0 (this pillar's existing "worst in
        # curve/percentile" value, same floor `_pb_curve_score`/`_ps_curve_score`/the
        # percentile mechanism already use) is exactly what a true E/P ranking would produce,
        # up to the ordering AMONG unprofitable names (which would need the actual EPS
        # magnitude to differentiate - not attempted here, same "no full-precision fix without
        # new data" tradeoff already accepted for the "computed-but-unscored" fields
        # elsewhere). `update_value_multiples_percentiles()`'s post_run() pass applies the
        # identical floor at the cross-sectional percentile stage - see that method's docstring.
        # EQUAL-WEIGHTED 2026-09-01 (/goal session: "lets get the weightings more normal the
        # 41% still seems wacky... is that what the industry players set these at too?").
        # Previous weights (12/41/35) were DATA-DRIVEN, not industry-standard - three separate
        # rounds of "give more weight to whichever multiple backtested strongest in OUR data"
        # (Margin of Safety's removal, EV/FCF's removal, Dividend Yield's trim all routed freed
        # weight to PB specifically). That's a defensible philosophy but not how real multi-
        # metric Value composites are built: Fama-French's classic HML uses book-to-market
        # ALONE (no blend at all); AQR and most practitioner multi-ratio Value composites
        # average book/price, earnings/price, and sales/price roughly EQUALLY, not skewed
        # toward whichever ratio happens to backtest strongest on one specific sample. User's
        # explicit direction: match the industry-conventional equal-weight-the-core-multiples
        # approach over this repo's own in-sample-optimized weights. P/E (27%) + P/B (27%) +
        # P/S (27%) equal-weighted core; Forward P/E (9%) and Dividend Yield (10%) stay smaller
        # satellite inputs (thinner history / weaker evidence respectively - neither is one of
        # the 3 "core" multiples in any of the cited methodologies).
        if metrics.get("pe_ratio") is not None and metrics["pe_ratio"] > 0:
            pe_score = self._pe_curve_score(metrics["pe_ratio"])
            weighted_sum += pe_score * 0.27
            total_weight += 0.27
        elif metrics.get("pe_ratio_unavailable_reason") == "unprofitable_stock":
            weighted_sum += 0.0 * 0.27
            total_weight += 0.27

        # P/B ratio: lower is better for value; < 3 is reasonable for most sectors.
        if metrics.get("pb_ratio") is not None and metrics["pb_ratio"] > 0:
            pb_score = self._pb_curve_score(metrics["pb_ratio"])
            weighted_sum += pb_score * 0.27
            total_weight += 0.27

        # P/S ratio: lower is better; thresholds sit higher than P/B since revenue
        # multiples run richer than book multiples (especially for growth/SaaS names).
        if metrics.get("ps_ratio") is not None and metrics["ps_ratio"] > 0:
            ps_score = self._ps_curve_score(metrics["ps_ratio"])
            weighted_sum += ps_score * 0.27
            total_weight += 0.27

        # PEG - REMOVED FROM SCORING 2026-08-28 (goal: "is this value score right per industry
        # best practice"). Prior passes (see "PEG - TRIMMED FURTHER, NOT REMOVED" docstring
        # note below) kept PEG at a small weight because its evidence tier (real univariate
        # signal, not a duplicate of anything else) didn't meet the wrong-signed/duplicate bar
        # that justified removing fcf_yield/ev_ebitda/ev_revenue - that reasoning answered
        # "does it work statistically", not "does it belong in a Value factor by definition".
        # PEG is explicitly a growth-ADJUSTED earnings multiple (PE divided by a growth rate) -
        # institutional multi-factor models deliberately keep Value and Growth as SEPARATE,
        # independently-measurable factors (that's the entire point of a multi-factor model -
        # a portfolio can tilt on one without the other), and no mainstream systematic Value
        # methodology (MSCI Enhanced Value, MSCI World Value, Russell, S&P Style, Barra,
        # Fama-French/AQR) includes a growth-blended ratio in its Value descriptor list - PEG is
        # a Peter Lynch individual-stock heuristic, not a factor-model input. This is the same
        # "does this belong here" axis margin_of_safety was removed on (see that docstring note
        # above), not a new statistical finding. peg_ratio stays fully computed/stored/displayed
        # (value_metrics.peg_ratio) - same "computed-but-unscored" convention as ev_ebitda/
        # ev_revenue/fcf_yield/margin_of_safety. Freed 3% went to Dividend Yield (8%->11%, see
        # its own weight comment below) - the only other input with the same "real but modest"
        # evidentiary tier PEG was previously grouped with, so it absorbs PEG's freed slot
        # rather than PE/PB/PS (whose relative weights reflect a separate, already-settled
        # robustness ranking - see their own weight comments above).

        # Forward P/E: MSCI's Value index methodology uses 12-month FORWARD Earnings/Price as
        # one of its three core descriptors (alongside Book/Price and Dividend Yield) - trailing
        # P/E above is the input every mainstream index actually swaps out in favor of this one.
        # ADDED 2026-08-28 (user directive, "get forward PE in here the right way... aligned
        # with industry standards") explicitly as a judgment call, not an evidence-based one:
        # analyst_earnings_estimates (load_analyst_earnings_estimates.py) only has ~22 trading
        # days of real history as of this change (started ~2026-08-03) and there is no vendor
        # source anywhere that exposes historical consensus estimates - yfinance's
        # Ticker.earnings_estimate is a live-only snapshot, so this field is fundamentally
        # unbacktestable today, not just untested. This is the same "user judgment overrides
        # backtest evidence" precedent already established for dividend_yield-vs-net_payout_yield
        # and the Amihud/Size episodes - institutional pedigree substitutes for local evidence
        # until enough daily snapshots accumulate (months, not something that can be sped up) to
        # actually test it. Reuses `_pe_curve_score`'s existing curve (same conceptual ratio, one
        # year further out - no principled reason to invent different thresholds sight-unseen)
        # as the Pass-1 provisional value, AND joins the cross-sectional percentile-rank
        # reconciliation in `update_value_multiples_percentiles()` alongside PE/PB/PS (see that
        # method's own docstring) - the same IBD/MSCI-style relative-ranking treatment already
        # validated for the other three multiples, extended here on the same logic rather than
        # left on a never-validated fixed curve. Weight 4% - deliberately SMALLER than PEG's 3%
        # is large relative to zero, but smaller than PEG's own 3%+institutional-pedigree combo
        # would otherwise suggest: forward P/E has real institutional standing but literally
        # zero local evidence (can't be tested at all yet), whereas PEG has at least a real, if
        # weak, univariate signal - a zero-evidence field shouldn't outweigh a some-evidence one
        # just because it took over what used to be a bigger slot.
        # UNPROFITABLE-FORECAST FLOOR ADDED 2026-08-28 (same fix and reasoning as P/E's own
        # "UNPROFITABLE-COMPANY FLOOR" note above). A real analyst forward-EPS estimate
        # projecting a LOSS next year (common for biotech/EV/early-growth names - live-confirmed
        # MRNA/RBLX/RIVN/RKLB/WBD/BNTX) leaves forward_pe undefined, and was previously just
        # skipped here rather than scored low - 848 of 1,560 universe "no_analyst_estimates"
        # forward_pe rows (54%) are actually this case
        # (`forward_pe_unavailable_reason == "negative_forward_eps"`), not genuine no-coverage.
        # Floored at 0, same as P/E's floor - any negative forward earnings yield is worse than
        # any non-negative one by definition.
        # Weight 9% (2026-09-01: raised from 4% as part of the equal-weight-the-core-multiples
        # reweight above - see that note. Kept as a smaller satellite weight, not equal to
        # PE/PB/PS, since analyst_earnings_estimates still has thin history (~22 trading days
        # at last check) that can't be backtested the way the 3 core trailing multiples were.
        if metrics.get("forward_pe") is not None and metrics["forward_pe"] > 0:
            fwd_pe_score = self._pe_curve_score(metrics["forward_pe"])
            weighted_sum += fwd_pe_score * 0.09
            total_weight += 0.09
        elif metrics.get("forward_pe_unavailable_reason") == "negative_forward_eps":
            weighted_sum += 0.0 * 0.09
            total_weight += 0.09

        # FCF yield REMOVED 2026-08-28 (see "FCF YIELD - RESOLVED 2026-08-28" docstring note
        # below): independently re-verified and confirmed robustly wrong-signed - higher
        # fcf_yield predicts LOWER forward returns in every window tested, gets worse under
        # scrutiny, meets the same two-independent-verification bar this file's other reversals
        # were held to. Its 9% weight went to PB (+3), PS (+2), and Margin of Safety (+4) above/
        # below - the most robust existing multiple and the most distinct existing diversifier,
        # not a clean ocf_yield replacement (see that docstring note for why ocf_yield itself
        # isn't a safe drop-in). fcf_yield stays fetched/computed/displayed
        # (sec_valuations.fcf_yield) - just no longer consumed here, same "computed but
        # unscored" convention as ev_ebitda/ev_revenue elsewhere in this file.

        # Dividend yield: bonus signal for income/quality. REVERTED 2026-08-28 from
        # net_payout_yield (dividends + buybacks) back to plain dividend_yield on explicit
        # user directive - see this function's docstring for the full history (net_payout_yield
        # had the stronger statistical case, t=3.05 multivariate vs. dividend_yield's t=1.55-
        # 2.28, but the user overrode that on judgment; same precedent as Amihud/Size
        # elsewhere in this file). sec_valuations.dividend_yield (migration 1146) is stored as
        # a decimal fraction (0.03 = 3%).
        # net_payout_yield ITSELF is unchanged and stays computed/stored - just no longer
        # consumed here, same "computed but unscored" convention as ev_ebitda/ev_revenue.
        # Weight 11% (2026-08-28, later same day: +3 from PEG's removal above - see "PEG -
        # REMOVED FROM SCORING 2026-08-28" docstring note - the only other input at PEG's same
        # "real but modest" evidentiary tier).
        # FIXED 2026-08-31 (goal: data-loading gap investigation - same bug class as the
        # "UNPROFITABLE-COMPANY FLOOR"/"UNPROFITABLE-FORECAST FLOOR" notes above, found while
        # auditing this file for the same pattern). value_metrics.dividend_yield is a REAL,
        # already-computed 0.0 (not NULL) for non-dividend-paying stocks -
        # dividend_yield_unavailable_reason='non_dividend_paying_stock' confirms live-checked:
        # 2,850 of 5,111 universe symbols (56%), ALL with dividend_yield=0.0 exactly, never
        # NULL. A `> 0` gate here treated that real, correctly-computed 0% yield exactly like
        # missing data, silently reweighting the 11% dividend term away onto PE/PB/PS/Forward
        # P/E instead of scoring it at the floor - the same selection-bias bug class already
        # fixed for P/E/Forward P/E's own unprofitable-company case, just unnoticed here
        # because the raw value was already correct (0.0, not NULL) so no `_unavailable_reason`
        # plumbing was needed to fix it - only the `is not None` vs `> 0` gate. 0% yield is
        # definitionally the worst end of any yield ranking, so div_score's own formula
        # (min(100, div*16.7)) already floors correctly at div=0 -> score=0 once the gate lets
        # it through.
        # DIVIDEND YIELD - TRIMMED 2026-08-31 (/goal session: factor-score review, "do what is
        # best here maybe 7-8%"). Kept as a scored input on explicit user directive (see this
        # docstring's REVERTED/"we want the dividend yield instead of that payout shit" note
        # above), but its own predictive evidence has never been strong: full-sample t=0.98-2.28
        # depending on spec, and the effect vanished entirely in the best-covered 2019-2024
        # sub-period (p=0.542) - see the REDESIGNED 2026-08-25 docstring note above, which
        # already flagged this exact weakness and cut the weight once before (to "a token
        # weight") for the same reason, prior to the 2026-08-28 revert back up to 11%. Trimmed
        # 11%->8% to size the weight to the evidence while still keeping the input the user
        # explicitly asked for - not removed, not left at a weight the data doesn't support.
        # Freed 3pts split proportionally to PB(+2)/PS(+1) above, the two strongest, most
        # robust multiples in this pillar.
        # RAISED 8%->10% 2026-09-01 (equal-weight-the-core-multiples reweight above, see
        # PE/PB/PS's own note) - still a smaller satellite weight than the 27% core multiples.
        if metrics.get("dividend_yield") is not None:
            div = min(metrics["dividend_yield"] * 100, 6)  # decimal -> percent, cap 6%
            div_score = min(100, div * 16.7)
            weighted_sum += div_score * 0.10
            total_weight += 0.10

        # Forward P/E REMOVED 2026-08-25, RE-ADDED 2026-08-28 - see "FORWARD P/E - ADDED
        # 2026-08-28" docstring note above and the scored block earlier in this function for
        # the current state. This note is kept only for history: analyst_earnings_estimates'
        # thin history (~3 weeks as of the original 2026-08-25 removal, ~22 trading days as of
        # the 2026-08-28 re-add) was and still is real - the re-add is a judgment call on
        # institutional pedigree, not a claim the data-depth concern was resolved.

        # EV/EBITDA and EV/Revenue REMOVED 2026-08-25 (goal: re-audit ALL stock_scores inputs
        # for the "counted twice" bug class already fixed elsewhere - Momentum's ROC-vs-
        # return-windows, Quality's double-counted debt_to_assets): measured directly (150mo
        # pooled correlation, n=45,806) ps_ratio and ev_revenue correlate r=1.00 (literally the
        # same signal - EV only adds net debt/share, negligible next to price for most names),
        # pe_ratio and ev_ebitda correlate r=0.93 (near-duplicate). Both fields are still
        # fetched/displayed (loaders/load_stock_scores.py's _get_value_metrics, scores page) -
        # only their consumption here was removed, same convention as other
        # computed-but-unscored fields in this file. Their freed 16pts (8% each) went to PB
        # (+6, the most genuinely distinct multiple per the same correlation pass - only
        # 0.32-0.38 correlated with pe/ps/ev_ebitda/ev_revenue), FCF yield (+6, real
        # near-uncorrelated diversifier, t=1.62), and Dividend yield/Margin of Safety (+2 each,
        # weaker but still genuinely distinct diversifiers) - see this function's docstring for
        # the full evidence and why PE/PS were deliberately left untouched (separate,
        # unreconciled dispute about their relative predictive ranking).

        # MARGIN OF SAFETY - REMOVED FROM SCORING 2026-08-28 (goal: "is margin of safety
        # typically a metric used in the value factor score... or is it typically used some
        # other way"). Prior passes (see "FULL VALUE PILLAR RE-AUDIT" docstring note above,
        # MARGIN OF SAFETY section) had already established it's not a *duplicate* signal
        # (pooled correlation with every other Value input is low, max |r|=0.21) - but that
        # answered "does it double-count", not "does it belong in this formula at all".
        # Re-examined against how the industry actually constructs a systematic Value factor:
        # every standard methodology this repo can point to (MSCI Enhanced Value's P/B,
        # P/Forward-E, EV/CFO; Russell's P/B-led Combined Style; S&P Style Indices' B/P, E/P,
        # S/P; Fama-French HML/AQR's book-to-market-led composites) is built from accounting
        # *yield* ratios computed directly from financials/market price - objective, requires
        # no forecast, comparable across thousands of names in one cross-section. DCF-based
        # "margin of safety" (Graham -> Klarman) is a different tool by design: it requires
        # per-company growth and discount-rate assumptions, and in practice is used as a
        # per-stock decision/screening rule by fundamental deep-value investors, not folded
        # into a systematic cross-sectional ranking factor - exactly because uniform
        # assumptions (this repo's own flat 9.5% discount rate, 15%/yr growth cap, both
        # already flagged as known biases above) inject name-specific noise into what's
        # supposed to be a comparable rank. This repo's own numbers are consistent with that:
        # PE/PB/PS are robust in EVERY sub-period tested (see notes above); MoS's t-stat
        # swings 0.30 -> 2.12 across the same two halves - real but not the kind of stable
        # signal a systematic factor score should be built on. margin_of_safety_pct and
        # intrinsic_value_per_share stay fully computed/stored (load_sec_valuations.py,
        # migration 1208) and are the Deep Value page's (DeepValueStocks.jsx) primary metrics
        # - their natural home, matching how the industry/practitioner literature actually
        # uses margin of safety. Same "computed-but-unscored" convention as ev_ebitda/
        # ev_revenue/amihud_illiquidity above; freed 11pts went to PB (+6) and PS (+5), see
        # their weight comments above.

        # SIZE (market cap) REMOVED from here 2026-08-26 - promoted to its own top-level
        # pillar, then RETIRED ENTIRELY 2026-08-28 (see BASE_PILLAR_WEIGHTS' own comment for
        # the full evidence trail - _score_size/_size_curve_score/update_size_percentiles no
        # longer exist in this file as of that date). market_cap is not scored anywhere in the
        # composite anymore, in Value or otherwise - it remains stored on value_metrics for
        # reference/display only. (Historical note, no longer current: an earlier same-day
        # memory record from 2026-08-26 described Size being removed entirely on user
        # directive before this file's own Value-pillar pass had caught up to that; both are
        # superseded by the 2026-08-28 retirement above.)

        # AMIHUD ILLIQUIDITY - added 2026-08-26, REMOVED the same day (full re-audit pass,
        # same day, later - see "FULL VALUE PILLAR RE-AUDIT" docstring note above, AMIHUD
        # ILLIQUIDITY section, for the full reasoning). Summary: the signal itself is real and
        # reproducible (multivariate t=2.99 full sample, t=2.37/1.91 both sub-period halves,
        # survives controlling for real market cap directly) - this was NOT removed for being
        # statistically weak. It was removed because Amihud/illiquidity is, in the standard
        # asset-pricing literature (Amihud 2002; Pastor-Stambaugh 2003), its OWN distinct risk
        # factor family, conceptually separate from "cheap relative to fundamentals" (which is
        # what Value/HML-style scores are supposed to measure) - and because the user
        # independently flagged it as not belonging here before any of that literature/
        # validation was pulled up. Field stays computed/stored
        # (technical_data_daily.amihud_illiquidity, migration 1232, still populated by
        # loaders/load_technical_indicators.py) for any future explicit ask; just not consumed
        # by this function, same "computed-but-unscored" convention as ev_ebitda/ev_revenue
        # above (forward_pe is no longer in this bucket - see the Forward P/E block above).

        if total_weight > 0:
            return weighted_sum / total_weight
        logger.debug(f"[STOCK_SCORES] No value metrics found to score for {symbol}")
        logger.debug(
            f"[STOCK_SCORES] Returning data_unavailable marker for value_score({symbol}) - no scoreable fields"
        )
        return {"symbol": symbol, "data_unavailable": True, "reason": "no_value_scores_computed"}

    # _score_size/_size_curve_score REMOVED 2026-08-28 (Size retired as a composite pillar -
    # see BASE_PILLAR_WEIGHTS for the full evidence trail: size_proxy's strong imputed-regime
    # coefficient reconfirmed as substantially an MNAR data-coverage artifact even after fixing
    # the specific coverage bugs the user required first; direct user directive "just get rid
    # of size"). market_cap itself is NOT deleted - value_metrics.market_cap keeps being
    # computed/stored unchanged by load_value_quality_growth_metrics.py, just no longer scored
    # into its own 0-100 size_score here.

    # _score_positioning REMOVED 2026-08-27 (Positioning retired as a composite pillar - see
    # BASE_PILLAR_WEIGHTS for the full evidence trail: A/D rating null across every methodology
    # tried, including a full-history 2000-2026 re-test; institutional_ownership/short_interest
    # untestable for lack of real historical depth; the pillar-level composite proxy itself
    # never significant and sign-flips across half-splits). The method used to live here -
    # weighted A/D rating (35%) + institutional ownership (30%) + short interest (25%) + short
    # interest % change (10%) - see git history (this file, pre-2026-08-27) for the full
    # docstring and implementation if ever revisited. A/D rating/institutional ownership/short
    # interest are still computed by load_positioning_metrics.py and displayed via the scores
    # API's informational positioning_inputs field - only this synthesized composite is gone.

    def _score_risk(self, metrics: dict[str, Any] | None, symbol: str) -> float | dict[str, Any]:
        """Score risk metrics on 0-100 scale using price volatility / risk-of-loss signals only.

        RENAMED 2026-08-26 (user directive): Stability -> Risk. Same computation
        (volatility/beta/downside-vol/max-drawdown), name only - the underlying
        stability_metrics input table and _get_stability_metrics accessor are unchanged.

        REWORKED 2026-08-30 (later same day, user directive: "figure out what is best here and
        do that" - full delegation after the 40/20/15/15 revert above was itself questioned).
        Current formula: Volatility 60D (45%) + Volatility 252D (20%) + Beta (20%) + Max
        Drawdown 1Y (15%). Reasoning per input, applying this file's own accumulated evidence
        rather than re-deriving it: Volatility 60D gets the largest share because it's the one
        robustly-significant signal in the whole panel (t=-6.07 multivariate). Volatility 252D
        stays for genuine horizon diversity - its correlation with 60D (0.69-0.89) is real but
        well short of the ~0.9+ band this file treats as actionable redundancy elsewhere.
        Volatility 30D is DROPPED: it's the most redundant of the three windows (least distinct
        horizon from 60D) and its removal doesn't lose a horizon 252D doesn't already cover
        from the other side. Beta is kept at a deliberate, non-alpha weight - scored for
        market-correlated swing-trading fit, not because it's return-predictive (it isn't,
        t=0.93 - see below). Max Drawdown 1Y returns at a modest weight as a genuinely distinct
        loss-severity dimension (a smooth-vol stock can still suffer one deep crash that vol
        windows don't capture) rather than as a return-prediction bet, since the 2026-08-25
        sub-period analysis below found it isn't stably predictive in either direction -
        consistent with how Beta is already scored here for a non-predictive reason. Downside
        volatility (all windows) and Debt-to-Assets stay OUT: both have clean, confirmed
        reasons below (downside_vol is pure redundancy, r=0.93 wrong-signed once vol_60d is
        controlled for; debt_to_assets is a balance-sheet solvency ratio, not a price-risk
        metric, and already scored under Quality) rather than open questions.

        The paragraphs below (40/20/15/15 revert, and before that the 60/20/20 consolidation)
        describe earlier same-day states and are now STALE history, not the current design.

        Uses weighted scoring: Volatility 60d (60%, absorbed downside_volatility_60d's freed
        15% 2026-08-28 - see REMOVED note below) + Beta (20%) + Max Drawdown 1y (20%). Lower
        volatility and beta closer to 1.0 indicate stable, market-correlated stocks. Weights
        are relative, not required to sum to 100 - each present
        sub-component contributes weighted_sum/total_weight (self-normalizing over whatever
        metrics are actually available for a symbol, per GOVERNANCE's no-redistribution rule at
        the top-level factor split; this renormalization is local to stability's own sub-scores).

        CLEANUP 2026-08-16: Financial Stability (debt-to-equity, debt-to-assets, current/quick
        ratio, cash per share) and Business Diversification (revenue concentration HHI) were
        removed from this factor - stability is meant to track price-volatility/risk-of-loss
        character, not balance-sheet fundamentals or business concentration. The debt/liquidity/
        cash metrics moved to Quality (at the time, via `_enhance_quality_score` - since removed
        2026-08-26; debt-to-equity is now a real 18%-weighted `_score_quality` input directly,
        not an enhancement bump - see that method's own docstring). Revenue concentration HHI
        was dropped from scoring entirely per user request.

        REWEIGHTED 2026-08-25 (goal: Fama-MacBeth factor-weighting pass, see
        algo/research/fama_macbeth_price_factors.py): built a proper monthly cross-sectional
        Fama-MacBeth panel (126 months, 2016-01 to 2026-06, median 3,409 symbols/month,
        z-scored factors, 1%/99% winsorized) regressing forward 1-month return on
        vol/downside_vol/beta/max_drawdown/momentum jointly - unlike the pooled-panel Spearman
        correlations used in the rest of this file's 2026-08-25 audit (which treat every
        symbol-month as an independent observation and understate correlation within a month,
        inflating significance), Fama-MacBeth averages one regression per month so the t-stats
        are month-count-limited (n=126), not observation-count-limited. Result: volatility_60d
        was the single strongest, most robust signal in the entire panel (multivariate
        coef=-0.0071/month, t=-6.07) - low vol robustly predicts higher forward return, same
        direction this pillar already scores it. downside_volatility_60d, once vol is in the
        regression alongside it, carries NO independent signal and comes out wrong-signed
        (coef=+0.0013, t=+1.39, i.e. not distinguishable from zero and if anything pointing the
        wrong way) - consistent with the 2026-08-25 stability consolidation's own finding that
        symmetric and downside volatility windows correlate 0.52-0.92 with each other; downside_vol
        is largely re-measuring what vol already captures. Moved 10pts of weight from
        downside_vol to vol accordingly. beta and max_drawdown weights left unchanged: beta's
        insignificance (t=0.93) doesn't call for a change since this pillar deliberately scores
        beta-near-1.0 for swing-trading fit, not as a return predictor (see below) - a flat
        regression coefficient doesn't contradict a non-alpha design goal. max_drawdown_1y came
        back wrong-signed too (coef=-0.0043, t=-1.65, i.e. bigger past drawdowns weakly
        associated with HIGHER forward returns, the opposite of what this pillar assumes) but
        only marginally (~p=0.10) - not strong enough evidence to flip a pillar's semantic
        meaning on a live-money system; flagged as an open question pending the named follow-up
        (sub-period stability, Newey-West-adjusted SE) rather than acted on that day.

        RESOLVED 2026-08-25 (same-day follow-up, goal: finish the named follow-up rather than
        leave it open): ran exactly that follow-up - univariate-only max_dd regression (isolates
        it from the multivariate collinearity that produced the -1.65 reading above), both a
        Newey-West(3-lag) HAC-adjusted SE on the full 127-month sample and a first-half/second-
        half/tercile sub-period split. Full-sample univariate signal is indistinguishable from
        zero (mean=+0.00017, naive t=0.07, Newey-West t=0.06 - HAC adjustment barely moves it,
        so serial correlation wasn't hiding a real effect either). More importantly it is NOT
        STABLE: first half (2016-01 to 2021-03, 63mo) is wrong-signed (t=-1.61, agreeing with
        the original multivariate finding's direction) while the second half (2021-04 to
        2026-07, 64mo) is right-signed (t=+1.75) - a clean sign flip across the sample, not
        random noise around one stable value. Terciles confirm the same pattern (weak-negative,
        weak-negative, then positive). Conclusion: the original wrong-signed multivariate
        reading was very likely a collinearity artifact from being jointly estimated alongside
        vol/downside_vol/beta/momentum (the same artifact class documented in Momentum's own
        multivariate coefficients elsewhere in this file), not a real, exploitable anomaly in
        either direction - there is no stable relationship here to flip the sign FOR. Correctly
        left as originally designed (higher/less-severe max_drawdown_1y scores better); this
        question is now closed with evidence rather than left open on caution alone.

        INDEPENDENT RE-VERIFICATION 2026-08-25 (same standard applied to the PE-vs-PB/PS
        finding in _score_value's docstring - digging in to be certain rather than trusting
        a claim already in the file, since that Value claim didn't fully reproduce when
        checked). Re-ran the sub-period split from scratch, independently: t-stats came back
        directionally consistent (full sample ~zero, first half negative, second half
        positive - the sign-flip pattern IS real) but meaningfully WEAKER than claimed above
        - full sample t=0.22 (vs claimed 0.07/0.06, both near-zero so roughly consistent),
        first half t=-0.57 (vs claimed -1.61), second half t=+0.77 (vs claimed +1.75). Same
        conclusion either way - no stable relationship, correctly left unflipped - but the
        magnitude of "wrong-signed in the first half" was overstated in the original claim;
        noting the more conservative numbers here rather than leaving the stronger, unverified
        ones as the only record. (Momentum's RSI decay finding, checked the same way, DID
        reproduce closely - see that pillar's docstring - so this isn't a blanket doubt on
        every inherited claim, just this specific one.)

        OPEN QUESTION flagged 2026-08-25 (same day, later pass - goal: check whether other
        canonical academic factors are still missing after adding Size to Value). Amihud
        (2002, Journal of Financial Markets) illiquidity - |monthly return| / average daily
        dollar volume, one of the most replicated liquidity-premium measures in empirical
        finance, alongside the related Brennan/Chordia/Subrahmanyam (1998, JFE) finding that
        raw dollar trading volume itself negatively predicts forward returns - is completely
        absent from this system. Tested directly from price_daily (which has full volume
        history, unlike technical_data_daily's ~3-month window): monthly Amihud illiquidity
        vs forward 1-month return, 126 months 2016-2026, median 3,866 symbols: t=3.34,
        positive (more illiquid = higher forward return, the expected illiquidity-premium
        direction). Checked it isn't just re-measuring Size first: correlation with
        log(market_cap) is only -0.18 (winsorized) - a real, distinct signal, not a
        duplicate. NOT implemented, unlike Size: Size only needed reading an already-stored
        field (market_cap on value_metrics); Amihud illiquidity needs a genuine new
        computation (daily |return|/dollar-volume averaged over a window) that no existing
        metrics table stores - technical_data_daily has volume_ma_20/50 columns, but they're
        100% NULL (computed nowhere) and that table only holds ~3 months of history even if
        populated. Implementing this needs upstream loader work (compute and store an
        illiquidity/dollar-volume metric with real historical depth, most naturally from
        price_daily where the raw OHLCV is), a bigger scope than a stock_scores.py-only
        change - flagged as the clearest remaining structural gap after Size, not rushed in.

        RETURN TYPES (STRICT):
        - available weight >= RISK_MIN_WEIGHT_AVAILABLE (0.40) → returns float (0-100)
        - metrics marked data_unavailable=True → returns marker dict (never None)
        - metrics is None or missing → returns marker dict (never None)
        - 0 < available weight < RISK_MIN_WEIGHT_AVAILABLE → returns marker dict with
          reason="insufficient_risk_inputs_thin_sample" (added 2026-08-31 - see that constant's
          own docstring, same thin-sample-extrapolation principle as Growth/Quality)
        - all risk fields None → returns marker dict with reason="no_risk_scores_computed"

        ERROR HANDLING:
        - Type conversion errors → RuntimeError (via _safe_float)
        - Negative volatility → treated as 0 (impossible case, but defensive)

        MINIMUM DATA REQUIREMENT: available weight (volatility_60d 0.45 + volatility_252d 0.20 +
        beta 0.20 + max_drawdown_1y 0.15) must reach RISK_MIN_WEIGHT_AVAILABLE (0.40) - see that
        constant's own docstring for why a single thin field (e.g. max_drawdown_1y alone) is no
        longer enough. If all stability metrics are None, returns data_unavailable marker.
        Critical metric for stock scoring (high priority upstream loader).
        """
        if not metrics or metrics.get("data_unavailable"):
            logger.warning(f"[STOCK_SCORES] Returning data_unavailable marker for risk_score({symbol})")
            return {"symbol": symbol, "data_unavailable": True, "reason": "no_risk_metrics_data"}

        weighted_sum = 0.0
        total_weight = 0.0

        # REWORKED 2026-08-30 (later same day, user directive: full delegation to figure out
        # the best combination - see this method's docstring for the per-input reasoning).
        # Volatility 60D 45% + Volatility 252D 20% + Beta 20% + Max Drawdown 1Y 15%.
        # Volatility 30D dropped (most redundant of the three windows). Debt-to-Assets stays
        # fetched via Quality's own debt_to_assets read (quality_inputs on the scores API) -
        # not merged into or scored by this pillar.

        if metrics.get("volatility_60d") is not None:
            v60_score = self._vol_curve_score(max(0, metrics["volatility_60d"]))
            weighted_sum += v60_score * 0.45
            total_weight += 0.45

        if metrics.get("volatility_252d") is not None:
            v252_score = self._vol_curve_score(max(0, metrics["volatility_252d"]))
            weighted_sum += v252_score * 0.20
            total_weight += 0.20

        # Beta: close to 1.0 is best, target 0.8-1.2 for market-correlated swing trading.
        # Deliberately not the literature's low-beta preference (Frazzini & Pedersen 2014
        # "Betting Against Beta") - this codebase consistently targets market-correlated
        # moves for swing-trading fit rather than minimum systematic risk, a repeated,
        # deliberate design choice, not an oversight.
        #
        # FIX 2026-08-28/29 (goal: composite-score review): beta used to be clipped to a floor
        # of 0 (`max(0, beta)`) before computing distance from 1.0 - the same defensive pattern
        # this function correctly applies to volatility/downside-vol/drawdown just above/below
        # (those are magnitudes, negative values are impossible data errors) but copied onto
        # beta without re-checking the semantics: beta is a signed regression coefficient, not a
        # magnitude, and real (if uncommon) inverse-correlated names legitimately have negative
        # beta. Clipping collapsed every negative beta to the SAME score regardless of how
        # negative - live-DB-confirmed: 548/5,009 symbols (~11% of the universe) have beta < 0,
        # ranging from -0.05 to -9.97, and ALL 548 scored an identical beta_score=50 before this
        # fix. Removing the clip lets |beta-1.0| grow past 2.0 for these names, which the
        # existing `min(diff, 2.0)` saturation already correctly floors to beta_score=0 - no
        # separate guard needed.
        if metrics.get("beta") is not None:
            beta = metrics["beta"]
            diff = min(abs(beta - 1.0), 2.0)
            beta_score = max(0, 100 - (diff * 50))
            weighted_sum += beta_score * 0.20
            total_weight += 0.20

        # Max drawdown (1y): peak-to-trough decline, stored as a negative percentage
        # (e.g. -34.63 = a 34.63% decline from peak). Distinct signal from volatility (a
        # stock can have low day-to-day volatility yet still suffer one deep sustained
        # drawdown). Scored as a loss-severity characterization, not a return-prediction bet -
        # see this method's docstring for why (not stably predictive either direction).
        if metrics.get("max_drawdown_1y") is not None:
            drawdown_pct = abs(min(0.0, metrics["max_drawdown_1y"]))
            dd_score = self._max_drawdown_curve_score(drawdown_pct)
            weighted_sum += dd_score * 0.15
            total_weight += 0.15

        if total_weight >= RISK_MIN_WEIGHT_AVAILABLE:
            return weighted_sum / total_weight
        if total_weight > 0:
            logger.info(
                f"[STOCK_SCORES] {symbol} risk_score withheld: only {total_weight:.2f}/1.00 weight "
                f"available, below RISK_MIN_WEIGHT_AVAILABLE={RISK_MIN_WEIGHT_AVAILABLE}. See that "
                f"constant's docstring - a thin-weight renormalization is not an honest partial score."
            )
            return {
                "symbol": symbol,
                "data_unavailable": True,
                "reason": "insufficient_risk_inputs_thin_sample",
            }
        logger.debug(f"[STOCK_SCORES] Returning data_unavailable marker for risk_score({symbol}) - no scoreable fields")
        return {"symbol": symbol, "data_unavailable": True, "reason": "no_risk_scores_computed"}

    def _score_momentum(self, metrics: dict[str, Any] | None, symbol: str) -> float | dict[str, Any]:
        """Score momentum metrics on 0-100 scale. Returns marker dict if no real data.

        Uses weighted scoring: Momentum 3m (20%) + 12-1 skip-month momentum (35%) + RSI(14)/
        MACD-sign technical-trend confirmation (37% combined, averaged - see CONSOLIDATED
        2026-08-28 note below) + SMA positioning (8%). Normalizes by total weight of
        available components so partial data doesn't deflate the score. Raw momentum_6m/
        momentum_12m REPLACED 2026-08-25 by a derived 12-1 construction - see RESOLVED note
        below.

        CONSOLIDATED 2026-08-28 (goal: momentum/risk factor-interaction review, closing a gap
        this file's own 2026-08-25 audit flagged and never finished - see "OPEN QUESTION
        flagged 2026-08-25" below: that FM panel found rsi_14/macd_sign correlated r=0.70, and
        their multivariate coefficients literally flip sign against each other under joint
        estimation (macd_sign t=-0.37 alone vs t=+2.95 jointly) - the textbook symptom of two
        inputs carrying substantially the same information, not two independent ones. That
        audit's own conclusion was "the right fix here is a consolidation pass ... before any
        reweighting", but only the momentum-window half of that pass (6m/12m -> 12-1, see
        RESOLVED note below) was ever actually done - RSI/MACD were left as two independently-
        weighted 21%/16% terms despite being named in the same finding. Live-reverified before
        acting, not trusted from a 3-day-old docstring number alone: current DB, rsi_14 vs
        (macd>0) Pearson r=0.58 (n=10,796, latest technical_data_daily row per symbol) - same
        conclusion, real and current, not a stale claim. Fixed the same way this pillar's own
        price_vs_sma_50/200 (r=0.87, same OPEN QUESTION) and Risk's six volatility windows
        (r=0.52-0.92) were already fixed: average the two 0-100 sub-scores into one slot
        instead of weighting each independently. Combined weight unchanged (21%+16%=37%) - a
        redundancy fix, not a new claim about RSI vs. MACD's relative signal strength.

        REDESIGNED 2026-08-25 (goal: full scoring-architecture audit): momentum_1m and the
        ROC composite both removed. ROC composite was pure redundancy - roc_20d/60d/120d/252d
        are the same `close.pct_change()` computation as momentum_1m/3m/6m/12m over
        near-identical trading-day windows, so it was the same 4 return windows counted a
        second time, not a diversifying signal. momentum_1m was dropped separately per the
        standard academic 12-1 momentum construction (Jegadeesh 1990 short-term reversal) -
        see the weights dict below for the empirical confirmation in our own data.

        OPEN QUESTION flagged 2026-08-25 (same day, later pass - goal: re-audit ALL stock_scores
        inputs without bias toward what already shipped): built
        algo/research/fama_macbeth_momentum_factors.py - reconstructs RSI(14)/MACD/SMA(50,200)
        directly from price_daily (Wilder 1978 RSI convention, standard 12/26/9 MACD EMAs) so
        the ENTIRE live Momentum input set (not just the 3m/6m/12m windows tested in
        fama_macbeth_price_factors.py) could be regressed jointly for the first time. Found
        severe multicollinearity, measured directly (121-month pooled correlation matrix):
        mom_12m/mom_6m r=0.83, rsi_14/macd_sign r=0.70, price_vs_sma_50/200 r=0.87,
        mom_3m/mom_6m r=0.69 - comparable in magnitude to the 0.52-0.92 range that justified
        consolidating Stability's 6 volatility windows down to 2, except this pillar's 6 inputs
        never got that treatment. Consequence: multivariate FM coefficients for mom_6m,
        macd_sign, and price_vs_sma_200 all FLIP SIGN between univariate and multivariate specs
        (e.g. macd_sign t=-0.37 alone vs t=+2.95 controlling for the others) - a classic
        collinearity symptom, meaning none of those multivariate coefficients are trustworthy
        standalone evidence for reweighting. The one factor that stayed directionally stable
        both ways was rsi_14 (t=-1.83 univariate, -1.89 multivariate) - consistently NEGATIVE,
        i.e. high RSI (overbought) weakly predicts LOWER forward return in this data, the
        mean-reversion/oscillator interpretation Wilder originally designed RSI for, not this
        pillar's current trend-following "higher RSI = more bullish" treatment. Lower
        evidentiary tier than the JoF-grade factors elsewhere in this file though - RSI is a
        technical-analysis heuristic without the same academic asset-pricing literature behind
        it, so this is an internal-data finding, not a replicated anomaly. The right fix here
        is a consolidation pass (fewer, less-redundant inputs, same treatment Stability
        already got) before any reweighting - extracting weights from an unstable collinear
        regression would just encode noise (see RESOLVED note below for what was actually
        done). (Growth's open question, previously cited here as the same-tier companion
        item, is now resolved - see that pillar's docstring.)

        CONFIRMATORY RE-RUN 2026-08-25 (same-day follow-up, goal: check whether this needed
        more than a re-statement before the next session touches it): re-ran
        fama_macbeth_momentum_factors.py fresh rather than relying on the numbers above.
        Univariate results for the four return-window factors are ALL statistically
        indistinguishable from zero: mom_12_1 (proper Jegadeesh 1990 skip-month construction,
        not a live input at the time of this run) t=1.04, mom_3m t=-0.88, mom_6m t=-0.38,
        mom_12m t=0.38 - none exceed |t|=1.1, so there is no "drop the weakest, keep the
        strongest" call available from significance alone (unlike Value's clean PB-is-most-
        distinct finding). mom_12_1 was nominally the strongest of the four - suggestive, not
        conclusive on significance, but real: it's the actual literature-standard momentum
        construction (Jegadeesh 1990/Jegadeesh-Titman 1993/Carhart 1997 UMD), not an ad hoc
        pick, independent of whether this internal sample confirms it.

        RESOLVED 2026-08-25 (same-day follow-up, acting on the next-step spec above):
        momentum_6m and momentum_12m REPLACED by a derived 12-1 skip-month construction,
        following the exact same "collapse redundant windows, keep the total category weight"
        treatment already applied to Stability's 6 volatility windows. momentum_6m was the
        most redundant "middle" window (r=0.69 with 3m, r=0.83 with 12m - correlated with
        both neighbors, contributing the least unique information of the three) and
        momentum_12m's simple trailing-return construction is exactly the recency-
        contaminated shape this pillar's docstring already flagged as a problem when it
        dropped momentum_1m for the same Jegadeesh 1990 reason above - that reasoning was
        never carried through to fix the 12m window itself until now. No new stored field
        needed: mom_12_1 (cumulative return from 12mo-ago to 1mo-ago) is algebraically
        derivable from momentum_12m and momentum_1m, both already fetched here -
        ((1+momentum_12m/100)/(1+momentum_1m/100) - 1)*100. Weight 35% = the exact combined
        weight momentum_6m(20%) + momentum_12m(15%) previously carried - a straight
        consolidation of the redundant windows' weight into the literature-correct
        construction, not a new claim about relative signal strength (this data's own
        univariate test above found none of the four constructions individually
        significant - the redistribution rests on redundancy + literature convention, the
        same evidentiary bar Stability's consolidation used, not on this session's t-stats).
        momentum_3m kept unchanged (least correlated of the trio, r=0.69 with 6m, a genuine
        short-horizon complement to the now-proper long-horizon signal).

        RSI SIGN QUESTION - sub-period-checked same session (same method that closed
        Stability's max_drawdown_1y question, see that pillar's docstring): unlike
        max_drawdown_1y, rsi_14's negative univariate coefficient is NOT a sign flip - it's
        directionally consistent negative in 3 of 4 sub-samples (full sample t=-1.91, first
        half 2016-06/2021-06 t=-2.07, tercile 1 t=-1.54, tercile 2 t=-1.60) but fades to
        indistinguishable-from-zero in the most recent ~3.5 years (second half t=-0.45,
        tercile 3 2023-02/2026-07 t=+0.08) - a decaying-but-not-reversing pattern, not noise
        flipping sign. Still NOT flipping this pillar's "higher RSI = more bullish" treatment:
        (1) even the strongest historical reading (t≈-2) is a technical-analysis heuristic
        without the JoF-grade literature backing behind Value/Growth's anomalies, (2) the
        effect is weakest exactly in the most recent period, so acting on it now would mean
        trading on a relationship that has already largely decayed away, the same
        McLean-Pontiff logic already applied to Growth's asset_growth_yoy elsewhere in this
        file. Correctly left as originally designed; this sub-question is closed (won't flip).

        INDEPENDENTLY RE-VERIFIED 2026-08-25 (same "dig in, be certain" pass that corrected
        Stability's max_drawdown_1y sub-period numbers and Value's PE-vs-PB/PS claim, both of
        which had overstated an already-in-file finding). This one reproduced closely on a
        from-scratch re-run: full sample t=-1.83, first half t=-1.97, second half t=-0.44,
        terciles -1.58/-1.73/+0.52 - all within a few hundredths to a few tenths of the
        numbers above, not the several-point gap found in the other two claims. Confidence in
        this specific finding is high; the conclusion (won't flip) stands unchanged.

        RETURN TYPES (STRICT):
        - metrics available with ≥1 scoreable field → returns float (0-100)
        - metrics marked data_unavailable=True → returns marker dict (never None)
        - metrics is None or missing → returns marker dict (never None)
        - all fields None → returns marker dict with reason="no_momentum_scores_computed"

        ERROR HANDLING:
        - Weak price-return momentum (±3%) → returns None for that timeframe (insufficient signal)
        - Missing historical prices → timeframe momentum is None (not guessed)

        MINIMUM DATA REQUIREMENT: At least one of 1m/3m/6m/12m momentum, RSI, MACD, or ROC must be
        available (not None). If everything is None/missing, returns data_unavailable marker.
        """
        if not metrics or metrics.get("data_unavailable"):
            logger.warning(f"[STOCK_SCORES] Returning data_unavailable marker for momentum_score({symbol})")
            return {"symbol": symbol, "data_unavailable": True, "reason": "no_momentum_metrics_data"}

        # Named weights (2026-08-25 redesign, see docstring): momentum_1m dropped as a
        # standalone scored timeframe - standard academic 12-1 momentum construction
        # (Jegadeesh 1990) deliberately excludes the most recent month's raw return. Our own
        # panel confirmed why: trailing-1m return vs forward-1m return showed Spearman=-0.031
        # (p=4.2e-97, short-term reversal), but a double sort controlling for 12-1 momentum
        # showed the reversal is concentrated almost entirely in low-momentum (losing) names
        # (-0.31 spread) while high-momentum names showed continuation instead (+0.39 spread) -
        # a flat weighted-sum score can't encode that interaction, so the conservative fix is
        # dropping the most-recent-month return as its own scored input. momentum_1m is still
        # read below (see mom_12_1 derivation) - as an input to the 12-1 construction Jegadeesh
        # 1990 actually specifies, not as a standalone score.
        weights = {
            "momentum_3m": 0.20,
        }

        weighted_sum = 0.0
        total_weight = 0.0
        for key, w in weights.items():
            if metrics.get(key) is not None:
                score = self._pct_to_score(metrics[key])
                if score is not None:  # Skip weak momentum (score=None)
                    weighted_sum += score * w
                    total_weight += w

        # 12-1 momentum (skip most-recent-month, Jegadeesh 1990 standard construction) -
        # REPLACES raw momentum_6m/momentum_12m 2026-08-25 (see docstring RESOLVED note).
        # Derived rather than requiring a new stored field: cumulative return from 12mo-ago to
        # 1mo-ago is algebraically (1+momentum_12m/100)/(1+momentum_1m/100) - 1, converted back
        # to a percentage number to match _pct_to_score's expected input convention. Guarded
        # against a near-zero denominator (would require momentum_1m ~ -100%, a stock price
        # going to ~zero in a month - not realistic for a scoreable position, but NaN/Infinity
        # guarded both directions per this codebase's standard convention regardless).
        mom_12m_raw = metrics.get("momentum_12m")
        mom_1m_raw = metrics.get("momentum_1m")
        if mom_12m_raw is not None and mom_1m_raw is not None:
            denom = 1.0 + mom_1m_raw / 100.0
            if abs(denom) > 1e-6:
                mom_12_1 = ((1.0 + mom_12m_raw / 100.0) / denom - 1.0) * 100.0
                if math.isfinite(mom_12_1):
                    mom_12_1_score = self._pct_to_score(mom_12_1)
                    if mom_12_1_score is not None:  # Skip weak momentum (score=None)
                        weighted_sum += mom_12_1_score * 0.35
                        total_weight += 0.35

        # RSI(14) + MACD sign, CONSOLIDATED (see CONSOLIDATED 2026-08-28 docstring note):
        # averaged into one "technical trend confirmation" slot, combined weight 0.37
        # (21%+16%, unchanged), same self-normalizing "average what's available, don't
        # double-weight correlated inputs" treatment this pillar already gives SMA-50/200
        # below and Risk gives its volatility windows.
        #
        # RSI(14): momentum-following curve (not mean-reversion) - higher RSI is more
        # bullish, with only a slight pullback at extreme overbought (>85) for reversal risk.
        #
        # MACD: sign only, not magnitude. MACD's raw value scales with the stock's price
        # level (a MACD of 2 means something different for a $10 stock vs a $500 stock), so
        # magnitude isn't comparable across symbols - use it purely as a bull/bear trend
        # confirmation signal.
        #
        # FIX 2026-08-18 (loader-health review, log-noise sweep): a prior commit speculatively
        # preferred a "macd_line" field, anticipating a migration that never actually happened
        # on this table - _prepare_batch_context()'s own query (~line 402-406) selects
        # "rsi_14, macd, sma_50, sma_200, close" from technical_data_daily and nothing else,
        # so metrics.get("macd_line") was provably always None, 100% of the time, for every
        # symbol, every run. (technical_data_daily has no macd_line column at all - a
        # same-named column DOES exist, but on a different table, momentum_metrics, added by
        # an unrelated migration 119 - not the same computation, not queried here.) The
        # resulting "legacy field" warning fired on ~4926/4930 symbols every single
        # stock_scores run - not a rare backward-compat path, pure log noise masking real
        # warnings, with zero effect on the actual score (this WAS already the only value
        # ever used). Reverted to using "macd" directly.
        tech_trend_scores = []
        if metrics.get("rsi_14") is not None:
            tech_trend_scores.append(self._rsi_to_score(metrics["rsi_14"]))
        macd = metrics.get("macd")
        if macd is not None:
            tech_trend_scores.append(70.0 if macd > 0 else 30.0 if macd < 0 else 50.0)
        if tech_trend_scores:
            weighted_sum += (sum(tech_trend_scores) / len(tech_trend_scores)) * 0.37
            total_weight += 0.37

        # ROC (Rate of Change) composite REMOVED 2026-08-25 (goal: full scoring-architecture
        # audit): roc_20d/60d/120d/252d are literally the same computation as
        # momentum_1m/3m/6m/12m above (both `close.pct_change()` over near-identical trading-
        # day windows - momentum_1m uses 21 trading days back vs roc_20d's 20, momentum_12m
        # and roc_252d both use exactly 252) - this wasn't a diversifying signal, it was the
        # same four numbers counted a second time. Removed rather than reweighted.

        # Price vs Moving Averages: premium over SMAs indicates uptrend
        sma_scores = []
        for sma_field in ["price_vs_sma_50", "price_vs_sma_200"]:
            sma_val = metrics.get(sma_field)
            if sma_val is not None:
                # Price above SMA = bullish: +10% above = 75, +20% above = 100, -10% below = 25.
                # FIXED 2026-08-28 (goal: momentum/risk factor review): comment previously
                # claimed +5%=75/+10%=100/-10% range (a ±10% saturation), but the formula
                # itself has always used /0.2, i.e. ±20% saturation - the comment and the code
                # disagreed with each other. Corrected the comment to describe what the code
                # actually does; no evidence on file favors either threshold over the other, so
                # the formula itself is left unchanged (this repo's standing convention is not
                # to change a scoring curve without empirical backing).
                sma_score = 50 + (sma_val / 0.2) * 50  # ±20% range maps to 0-100
                sma_scores.append(min(100, max(0, sma_score)))
        if sma_scores:
            weighted_sum += (sum(sma_scores) / len(sma_scores)) * 0.08
            total_weight += 0.08

        if total_weight > 0:
            return weighted_sum / total_weight
        logger.debug(
            f"[STOCK_SCORES] Returning data_unavailable marker for momentum_score({symbol}) - no scoreable fields"
        )
        return {"symbol": symbol, "data_unavailable": True, "reason": "no_momentum_scores_computed"}

    @staticmethod
    def _pct_to_score(pct_return: float) -> float | None:
        """Convert percentage return to 0-100 score.

        Returns None if momentum is weak (< ±3%), as this indicates
        insufficient conviction. Fail-fast: weak signal is missing data, not low score.
        -20% = 0, ±3% = None, +20% = 100.

        pct_return is a percentage NUMBER (e.g. 20.0 for +20%), not a fraction - matches
        load_risk_metrics_daily.py's ret_pct = (price_new - price_old) / price_old * 100,
        which is what momentum_1m/3m/6m/12m are computed as and stored as.
        """
        # Weak momentum zone: -3% to +3% lacks conviction. This previously checked
        # -0.03 <= pct_return <= 0.03 - a threshold 100x too small for the percentage-number
        # scale pct_return is actually on, so it matched essentially no real momentum value
        # (typical 1m/3m/6m/12m returns are single-to-double-digit percent) and this weak-
        # signal exclusion never fired in practice - every momentum reading, however weak,
        # was scored instead of being excluded as insufficient conviction per the documented
        # design intent.
        if -3 <= pct_return <= 3:
            return None

        # Map momentum: -20% = 0, +20% = 100
        score = 50 + (pct_return / 0.4)
        return max(0, min(100, score))

    @staticmethod
    def _rsi_to_score(rsi: float) -> float:
        """Map RSI(14) to a momentum-following 0-100 score (higher RSI = more bullish).

        This is deliberately NOT a mean-reversion mapping (which would penalize high RSI as
        "overbought"). For a momentum factor, sustained strength (RSI 50-85) should score
        well; only extreme overbought (>85) gets a mild pullback for reversal risk.
        """
        rsi = max(0.0, min(100.0, rsi))
        if rsi <= 30:
            return (rsi / 30) * 30
        if rsi <= 50:
            return 30 + ((rsi - 30) / 20) * 20
        if rsi <= 70:
            return 50 + ((rsi - 50) / 20) * 35
        if rsi <= 85:
            return 85 + ((rsi - 70) / 15) * 15
        return max(60.0, 100 - (rsi - 85) * 3)

    @staticmethod
    def _pe_curve_score(pe: float) -> float:
        """PROVISIONAL fixed-threshold P/E score (see _score_value's PE block comment) - used
        as this symbol's Pass-1 placeholder only. UPDATED 2026-08-31 (see
        update_value_multiples_percentiles()'s "BUG FOUND + FIXED 2026-08-31" docstring note):
        that method now fully recomputes value_score from percentile ranks each time rather
        than diffing against this function's output, so this formula is free to change without
        touching that reconciliation - it only affects Pass-1's provisional value."""
        if pe <= 10:
            return 40 + pe * 2  # very cheap / possibly value trap
        if pe <= 20:
            return 60 + (pe - 10) * 4  # good range
        if pe <= 35:
            return 100 - (pe - 20) * 2  # growth premium zone -> 70 at pe=35
        return max(0.0, 70 - (pe - 35) * 1.4)  # expensive -> 0 at pe~85

    @staticmethod
    def _pb_curve_score(pb: float) -> float:
        """PROVISIONAL fixed-threshold P/B score - see `_pe_curve_score`'s docstring for why
        this must stay unchanged independent of the live scoring path."""
        if pb <= 1.0:
            return 100.0
        if pb <= 3.0:
            return 100 - ((pb - 1.0) / 2.0) * 30  # 100->70 in [1,3]
        if pb <= 7.0:
            return 70 - ((pb - 3.0) / 4.0) * 40  # 70->30 in [3,7]
        return max(0.0, 30 - (pb - 7.0) * 3)

    @staticmethod
    def _ps_curve_score(ps: float) -> float:
        """PROVISIONAL fixed-threshold P/S score - see `_pe_curve_score`'s docstring for why
        this must stay unchanged independent of the live scoring path."""
        if ps <= 2.0:
            return 100.0
        if ps <= 6.0:
            return 100 - ((ps - 2.0) / 4.0) * 30  # 100->70 in [2,6]
        if ps <= 15.0:
            return 70 - ((ps - 6.0) / 9.0) * 40  # 70->30 in [6,15]
        return max(0.0, 30 - (ps - 15.0) * 1.5)

    @staticmethod
    def _vol_curve_score(vol: float) -> float:
        """Fixed-threshold volatility score for volatility_60d (downside_volatility_60d REMOVED
        from scoring 2026-08-28 - see _score_risk's docstring - this curve no longer scores it,
        though the same threshold family as `_pe_curve_score`/`_pb_curve_score`/
        `_ps_curve_score` still applies). `vol` must already be non-negative (callers clamp via
        max(0, ...))."""
        if vol <= 0.15:
            return 100.0
        if vol <= 0.30:
            return 100 - ((vol - 0.15) / 0.15) * 50
        if vol <= 0.60:
            return 50 - ((vol - 0.30) / 0.30) * 40
        return max(0.0, 10 - (vol - 0.60) * 20)

    @staticmethod
    def _max_drawdown_curve_score(drawdown_pct: float) -> float:
        """Fixed-threshold max-drawdown score. `drawdown_pct` is a non-negative magnitude
        (e.g. 34.63 for a 34.63% peak-to-trough decline) - callers pass
        `abs(min(0.0, max_drawdown_1y))`."""
        if drawdown_pct <= 10:
            return 100 - drawdown_pct * 2  # 100->80
        if drawdown_pct <= 25:
            return 80 - (drawdown_pct - 10) * 2  # 80->50
        if drawdown_pct <= 50:
            return 50 - (drawdown_pct - 25) * 1.2  # 50->20
        return max(0.0, 20 - (drawdown_pct - 50) * 0.4)

    def _value_metrics_coverage_excluding_fpi(self, cur: Any) -> tuple[int, int] | None:
        """Return (covered, total) for value_metrics over the active, non-FPI universe.

        See audit_upstream_coverage()'s 2026-08-21 fix comment for why the raw
        data_loader_status.completion_pct is unusable for this gate: it counts every
        foreign-private-issuer symbol's permanent, correct value_metrics exclusion as a
        "failure" alongside genuine loader breakage.
        """
        try:
            cur.execute(
                """
                SELECT
                  COUNT(*) FILTER (WHERE v.data_unavailable IS NOT TRUE) AS covered,
                  COUNT(*) AS total
                FROM value_metrics v
                JOIN stock_symbols s ON s.symbol = v.symbol
                LEFT JOIN LATERAL (
                    SELECT is_foreign_private_issuer FROM company_info_sec c
                    WHERE c.symbol = v.symbol ORDER BY filing_date DESC LIMIT 1
                ) cis ON true
                WHERE s.active = true AND COALESCE(cis.is_foreign_private_issuer, false) = false
                """
            )
            row = cur.fetchone()
            if not row or not row[1]:
                return None
            return int(row[0]), int(row[1])
        except Exception as e:
            logger.warning(f"[STOCK_SCORES] Could not compute FPI-excluded value_metrics coverage: {e}")
            return None

    def audit_upstream_coverage(self) -> None:
        """Audit upstream metric loader coverage after stock_scores completes.

        Verifies that critical metric loaders (value_metrics, stability_metrics) have
        sufficient completion before considering stock_scores run successful.
        Prevents silent data degradation when upstream loaders fail to complete.
        """
        try:
            with DatabaseContext("read") as cur:
                cur.execute("""
                    SELECT
                        table_name,
                        completion_pct,
                        symbols_loaded,
                        symbol_count
                    FROM data_loader_status
                    WHERE table_name IN ('value_metrics', 'stability_metrics', 'growth_metrics')
                    ORDER BY table_name
                """)

                metric_coverage = cur.fetchall()
                if not metric_coverage:
                    logger.warning(
                        "[STOCK_SCORES] No upstream metric loader status found. Metrics may not be populated yet."
                    )
                    return

                # Require at least 95% coverage on critical metric loaders for real-money readiness
                min_coverage_pct = 95.0
                critical_metric_loaders = ["value_metrics", "stability_metrics"]
                # FIX 2026-08-10: value_metrics/quality_metrics/growth_metrics' data_loader_status
                # row is SHARED across every invocation of load_value_quality_growth_metrics.py,
                # including small scoped `--symbols` diagnostic/spot-check runs (e.g. re-verifying
                # a couple of symbols after a data fix). completion_pct/symbol_count reflect
                # whatever the MOST RECENT run's own requested scope was, not the real universe -
                # live-reproduced: a 2-symbol diagnostic run that legitimately failed both (unrelated
                # missing SEC valuation data) left symbol_count=2/symbols_loaded=0, which this audit
                # then read as "value_metrics is 0.0% complete" and hard-failed EVERY subsequent
                # stock_scores run universe-wide, even though the real full-universe run moments
                # earlier had already loaded 5699/4917 symbols successfully. A tiny symbol_count is
                # not a statistically meaningful sample of universe-wide health - require the row to
                # actually represent a full-universe run before trusting its percentage.
                min_representative_symbol_count = 1000

                for table_name, completion_pct, symbols_loaded, symbol_count in metric_coverage:
                    if completion_pct is None:
                        logger.warning(f"[STOCK_SCORES] {table_name}: completion_pct is NULL (loader still running?)")
                        continue

                    if table_name not in critical_metric_loaders:
                        continue

                    if not symbol_count or symbol_count < min_representative_symbol_count:
                        logger.warning(
                            f"[STOCK_SCORES] {table_name}: symbol_count={symbol_count} is too small to represent "
                            f"the full universe (likely a scoped/diagnostic run) - skipping the {min_coverage_pct}% "
                            f"coverage gate for this table rather than judging universe-wide health from a "
                            f"non-representative sample."
                        )
                        continue

                    # FIXED 2026-08-21 (goal session - "why is stock_scores intermittently
                    # stale"): value_metrics' own completion_pct counts a symbol as "failed"
                    # whenever its row-level data_unavailable=TRUE (see
                    # load_value_quality_growth_metrics.py's symbols_failed bookkeeping) - but
                    # the overwhelming majority of those are foreign private issuers, which
                    # load_sec_valuations.py deliberately and permanently refuses to compute
                    # market_cap/pe/pb/etc. for (20-F/40-F filers report share counts in
                    # non-ADS home-market units - see that file's shares_outstanding
                    # resolution comments). Live-confirmed: of 982 active symbols with
                    # value_metrics.data_unavailable=TRUE, 795 (81%) are FPIs - a permanent,
                    # correct exclusion, not a loader health signal. That inflates the
                    # "failure" count enough that this gate hard-failed the whole stock_scores
                    # run today (80.8% raw vs the 95% bar) even though the loader had actually
                    # completed cleanly. Recomputing coverage over the non-FPI universe only
                    # (the population this gate can actually judge loader health from) gives
                    # 95.37% for the exact same run - real, achievable, and still enforces the
                    # gate's actual intent (catch real upstream breakage) without punishing an
                    # already-verified structural gap.
                    if table_name == "value_metrics":
                        corrected = self._value_metrics_coverage_excluding_fpi(cur)
                        if corrected is None:
                            logger.warning(
                                "[STOCK_SCORES] value_metrics: could not compute FPI-excluded "
                                "coverage, falling back to raw completion_pct"
                            )
                        else:
                            symbols_loaded, symbol_count = corrected
                            completion_pct = (symbols_loaded / symbol_count * 100.0) if symbol_count else 100.0

                    if completion_pct < min_coverage_pct:
                        raise RuntimeError(
                            f"[STOCK_SCORES] Post-run audit failed: {table_name} only {completion_pct:.1f}% complete "
                            f"({symbols_loaded}/{symbol_count} symbols). "
                            f"Cannot compute stock scores with upstream metric coverage below {min_coverage_pct}%. "
                            f"Requires upstream metric loaders to complete successfully."
                        )
        except RuntimeError:
            raise
        except Exception as e:
            logger.error(f"[STOCK_SCORES] Post-run audit encountered error: {e}", exc_info=True)
            raise

    def post_run(self) -> None:
        # ORDER MATTERS: update_rs_percentiles() reads only momentum_score, which is
        # unrelated to what audit_upstream_coverage() checks (value_metrics/stability_metrics
        # coverage). Live-reproduced 2026-08-10: a transient dip in value_metrics coverage
        # (contention from concurrent sessions) made audit_upstream_coverage() raise, which
        # crashed the whole subprocess (exit 1) BEFORE update_rs_percentiles() ever ran - even
        # though all 4917 symbols' per-symbol scoring (including momentum_score) had already
        # completed successfully. rs_percentile stayed NULL for the entire universe, and
        # Phase 7 silently filtered out every single candidate as a result (100+ candidates
        # otherwise qualified) with a misleading "no signals found" message that never named
        # the real cause. Compute the RS ranking first (it doesn't depend on the audited
        # tables), THEN run the audit - a coverage problem should still fail the run for
        # visibility, but must not collaterally block an unrelated, Phase-7-critical step.
        self.update_rs_percentiles()
        # Must run before snapshot_score_history() so the history snapshot captures the
        # CORRECTED value_score/composite_score, not Pass 1's provisional fixed-curve values -
        # see update_value_multiples_percentiles()'s own docstring for the full evidence trail.
        self.update_value_multiples_percentiles()
        # update_size_percentiles() REMOVED 2026-08-28 (Size retired as a composite pillar -
        # see BASE_PILLAR_WEIGHTS for the full evidence trail).
        self.snapshot_score_history()
        self.audit_upstream_coverage()

    def update_rs_percentiles(self) -> None:
        """Batch pass: rank all stocks by momentum_score and write true RS percentile.

        Uses PERCENT_RANK() so a stock scoring higher than 90% of peers gets rs_percentile=90.
        Must run after all per-symbol scores are loaded.

        GOVERNANCE: PostgreSQL sorts NULLs last by default, so ranking over the full table
        (including rows with no momentum_score) previously gave every NULL-momentum stock a
        false top-quintile rs_percentile (~81, the percentile of the last real row) instead
        of reflecting that the stock has no momentum data at all. That fabricated value fed
        straight into Phase 7's signal-generation completeness gate, defeating the exact
        check meant to catch missing data. Rank only over rows with real momentum_score, and
        explicitly null out rs_percentile for the rest so missing data stays visibly missing.

        CRITICAL: Raises on failure. RS percentiles are essential for ranking signal quality;
        missing or stale percentiles invalidate momentum-based signal filtering.

        CRITICAL FIX 2026-08-06: Update `updated_at` timestamp to ensure Phase 1's freshness
        check recognizes that post_run() completed successfully and rs_percentile was computed.
        Without this, rs_percentile stays NULL and Phase 7 filters out all signals.
        """
        try:
            with DatabaseContext("write") as cur:
                # First, update rs_percentile via PERCENT_RANK for symbols with momentum scores
                cur.execute("""
                    UPDATE stock_scores ss
                    SET rs_percentile = ranked.pct,
                        updated_at = CURRENT_TIMESTAMP
                    FROM (
                        SELECT symbol,
                               ROUND(
                                   (PERCENT_RANK() OVER (ORDER BY momentum_score))::NUMERIC * 100,
                                   2
                               ) AS pct
                        FROM stock_scores
                        WHERE momentum_score IS NOT NULL
                    ) ranked
                    WHERE ss.symbol = ranked.symbol
                """)
                # Second, explicitly null out rs_percentile for symbols without momentum scores
                cur.execute("""
                    UPDATE stock_scores
                    SET rs_percentile = NULL,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE momentum_score IS NULL AND rs_percentile IS NOT NULL
                """)
                # Third, update timestamp for any remaining rows to mark post_run completion
                cur.execute("""
                    UPDATE stock_scores
                    SET updated_at = CURRENT_TIMESTAMP
                    WHERE rs_percentile IS NOT NULL OR momentum_score IS NOT NULL
                """)
            logger.info("RS percentiles updated via batch rank (post_run completed)")
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            error_msg = f"RS percentile batch update failed - stock scores cannot be finalized: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e

    @staticmethod
    def _percent_rank_cheap_high(values: dict[str, float]) -> dict[str, float]:
        """symbol -> percentile in [0, 100], where the LOWEST raw value gets the HIGHEST
        percentile (100) - matches this pillar's "cheap is good" convention for P/E, P/B, P/S.
        Ties share the same percentile (RANK()-style, not average-rank - matches PostgreSQL's
        own PERCENT_RANK() tie behavior, the same window function `update_rs_percentiles()`
        already uses for rs_percentile). A universe of 1 symbol gets 50.0 (no peer to rank
        against); empty input returns {}.
        """
        n = len(values)
        if n == 0:
            return {}
        if n == 1:
            return dict.fromkeys(values, 50.0)
        sorted_items = sorted(values.items(), key=lambda kv: kv[1])
        result: dict[str, float] = {}
        i = 0
        while i < n:
            j = i
            while j < n and sorted_items[j][1] == sorted_items[i][1]:
                j += 1
            pct = 100.0 * (n - 1 - i) / (n - 1)
            for sym, _ in sorted_items[i:j]:
                result[sym] = pct
            i = j
        return result

    @staticmethod
    def _components_with_corrected_value(components_old: Any, value_score_new: float) -> str:
        """Return components (the Pass-1 JSON breakdown dict) re-serialized with its 'value'
        key set to value_score_new, every other pillar untouched.

        BUG FIX 2026-08-29 (goal-mode composite-score validation pass): update_value_multiples_
        percentiles()'s UPDATE previously wrote value_score/composite_score but never touched
        components - which still held the Pass-1 provisional (fixed-curve) value, not the
        corrected cross-sectional-percentile one this method's caller just computed. Live-
        audited: 4690/4708 scored symbols (99.6%) had components->'value' disagreeing with the
        real value_score column, by up to 94 points on a 0-100 scale. Not currently read by the
        scores API (lambda/api/routes/scores.py rebuilds its breakdown from the individual
        *_score columns directly), so this was a latent data-integrity bug, not a live user-
        facing one - fixed anyway since components is a real field in the API response model
        (lambda/api/models/responses.py) and a direct DB consumer would be misled.

        components_old comes back from psycopg2 already parsed to a dict for a real jsonb
        value; the str/None branches are defensive only (a symbol with no Pass-1 components at
        all shouldn't reach here, since value_score - required for this batch pass's own SELECT
        WHERE clause - is only ever set alongside components in Pass-1).
        """
        if isinstance(components_old, dict):
            components_new = dict(components_old)
        elif components_old:
            components_new = json.loads(components_old)
        else:
            components_new = {}
        components_new["value"] = value_score_new
        return json.dumps(components_new)

    def update_value_multiples_percentiles(self) -> None:
        """Batch pass: replace P/E, P/B, P/S, and Forward P/E's Pass-1 PROVISIONAL fixed-curve
        scores with a true cross-sectional percentile rank against the current run's universe,
        then FULLY RECOMPUTE value_score and composite_score from scratch off the raw stored
        inputs (not patched relative to whatever value_score/composite_score currently hold).
        Mirrors `update_rs_percentiles()`'s pure-overwrite pattern, not the additive-delta
        design this method used until the rewrite below - see "BUG FOUND + FIXED 2026-08-31"
        below.

        EXTENDED TO FORWARD P/E 2026-08-28 (see _score_value's "FORWARD P/E - ADDED 2026-08-28"
        docstring note): when Forward P/E was added to Value, it joined this percentile mechanism
        on the same logic that already applies to the other three multiples below, rather than
        being left on a fixed curve nothing has validated for this specific field. FCF yield,
        PEG, and Margin of Safety were all LATER removed from Value scoring entirely (same day,
        later passes - see _score_value's docstring "FCF YIELD - RESOLVED", "PEG - REMOVED FROM
        SCORING", and "MARGIN OF SAFETY - REMOVED FROM SCORING" notes) - none of the three
        appear in total_weight_old below anymore. PEG was never part of the percentile-rank
        mechanism even while it was still scored (not a multiple needing a peer-relative
        construction the way P/E/P/B/P/S/forward_pe do), so removing it only meant dropping it
        out of total_weight_old, same treatment FCF yield already got.

        UNPROFITABLE/NEGATIVE-FORECAST FLOOR ADDED 2026-08-28 (same-day, later pass - see
        _score_value's "UNPROFITABLE-COMPANY FLOOR ADDED 2026-08-28" / "UNPROFITABLE-FORECAST
        FLOOR ADDED 2026-08-28" docstring notes): P/E and Forward P/E previously EXCLUDED
        unprofitable/negative-forecast symbols from both the percentile universe and
        total_weight_old, same selection-bias bug class this method's own WHY section already
        flags for the PE-vs-PB/PS ranking dispute. Now: such symbols are identified via
        `pe_ratio_unavailable_reason == "unprofitable_stock"` /
        `forward_pe_unavailable_reason == "negative_forward_eps"`, floored at percentile 0.0
        (the worst - any negative earnings yield is worse than any non-negative one by
        definition), and DO count in total_weight_old at the normal 0.12/0.04 weight - matching
        _score_value's Pass-1 treatment exactly so the delta-reconciliation math stays internally
        consistent (both OLD and NEW are 0.0 for these symbols' PE/Forward-P/E term, so this
        correction pass contributes no further delta for them on that specific term - the
        definitive floor score was already assigned in Pass 1).

        WHY (goal 2026-08-28, "what does IBD/the best and brightest do - rethink this and do it
        that way"): every credible external methodology checked this session scores value/
        quality inputs via CROSS-SECTIONAL RANKING against a peer universe, never a fixed
        absolute threshold -
          - IBD: "All stocks are arranged in order of ... percentage change and assigned a
            percentile rank from 99 (highest) to 1 (lowest)" for EVERY SmartSelect rating
            (EPS Rank, RS Rating, SMR Rating) - https://ibdstock.com/ibd-stock-ratings-explained/
          - MSCI: "z-score: zi = (xi - mu) / sigma ... across the universe" for value/quality
            factors - https://www.msci.com/research-and-insights/blog-post/the-theory-of-value-relativity
        This file's OWN Momentum pillar already does this correctly (`update_rs_percentiles()`,
        below - a proven precedent this method mirrors) - Value's P/E/P/B/P/S never got the
        same treatment, still using hand-set thresholds (`_pe_curve_score`/`_pb_curve_score`/
        `_ps_curve_score`, e.g. "P/E<=10 -> one formula, <=20 -> another") that don't adapt to
        the market's actual valuation regime at any point in time - a well-documented weakness
        of absolute thresholds vs. relative ranking in exactly this context.

        VALIDATED, not just asserted (algo/research/value_absolute_curve_vs_relative_ranking_20260828.py,
        same complete-case Fama-MacBeth methodology as every other change this session):
        cross-sectional percentile beat the live fixed curve in EVERY era and spec tested -
        multivariate t: FULL 0.98->2.02, ERA1 -0.75->0.12, ERA2 2.48->3.06; univariate t: FULL
        2.06->3.29, ERA1 0.57->1.38, ERA2 2.55->3.48. A 5-year-own-history TIME-SERIES leg (the
        other half of MSCI's own recommended hybrid) was ALSO tested and did NOT help on this
        repo's actual data (t=-0.44 to -0.10, flat/negative) - not implemented, since the
        evidence for it specifically doesn't hold here even though the citation is real.

        MECHANISM: Pass 1 (`_score_value`, per-symbol, no access to the universe distribution)
        still uses `_pe_curve_score`/`_pb_curve_score`/`_ps_curve_score` (the last one reused for
        Forward P/E too, same curve, see that field's own docstring note) as a PROVISIONAL
        placeholder so value_score/composite_score are never NULL mid-run. This method runs
        after every symbol in this run has a value_score, computes the true cross-sectional
        percentile per ratio (independently - a symbol missing P/B still gets ranked on P/E and
        P/S), and FULLY RECOMPUTES value_score from the percentile scores plus dividend_yield's
        own unchanged curve score (the only Value sub-component this pass doesn't replace),
        weighted exactly as `_score_value` itself weights them (12/39/34/4/11). composite_score
        is then independently recomputed in full from quality_score/growth_score/risk_score/
        momentum_score (read as-is, untouched by this pass) plus the new value_score, via
        `_value_risk_adjusted_weights` - the same weighting `_score_value`'s own caller uses,
        just re-derived here rather than patched.

        BUG FOUND + FIXED 2026-08-31 (goal session: "VCIG tops the scores and it's a shitty
        stock, dig in" - live-verified, this code is byte-identical to main, so this was live on
        production too, not a worktree artifact). The original design computed
        `value_score_NEW = value_score_OLD + delta`, reading `value_score_OLD` from the SAME
        mutable `stock_scores.value_score` column this method writes to - non-idempotent, since
        this batch pass runs unconditionally on the WHOLE universe on every single invocation of
        this loader's post_run(), regardless of `--symbols` scope (same bug class just found and
        fixed in `loaders/load_value_quality_growth_metrics.py`'s
        `update_quality_roe_roce_percentiles()` - see that method's own "BUG FOUND + FIXED
        2026-08-31" docstring note, which this fix mirrors exactly). Live-confirmed via two
        consecutive live calls today with zero underlying pe/pb/ps/forward_pe changes: TAP.A
        drifted 89.69 -> 83.70 -> 77.71 and CMCT drifted 81.84 -> 81.66 -> 81.48, the SAME delta
        applied twice on top of the prior call's already-corrected value instead of being
        computed fresh against a stable baseline - zero natural convergence, only the hard
        0/100 clamp eventually stops the drift (VCIG/BMA/CISS/AAPL/MSFT were already pinned at
        100.00/100.00/100.00/0.00/0.00 in this same test, consistent with the clamp already
        having been reached repeatedly in the normal pipeline cadence). This was the main
        mechanism - not just a one-time winsorization gap - behind multiple real, legitimate
        tickers (BMA, a large Argentine bank; CISS; TAP.A) clustering at or near the 0/100
        ceiling/floor on value_score well before any single pass's own math would justify it.
        Fixed by making this a pure function of the raw stored ratio/pillar columns, matching
        `update_rs_percentiles()`'s correct pattern - value_score and composite_score are now
        only ever WRITE targets here, never also read inputs, so running this any number of
        times with unchanged inputs produces the identical result every time.

        NOTE (separate, NOT fixed by this pass): `_percent_rank_cheap_high` itself has no
        winsorization - the single most extreme raw P/B or P/S in the entire universe always
        wins percentile 100 regardless of whether that extremeness is genuine undervaluation or
        a data/accounting artifact (live-confirmed: VCIG's pb_ratio=0.01/ps_ratio=0.02, tied for
        the cheapest in a 4,500+-symbol universe, both win percentile 100/99.8 outright). This is
        a real, standard-practice gap (MSCI's own cited z-score methodology conventionally
        winsorizes before ranking) distinct from the compounding bug above, and is a candidate
        for a future pass - not addressed here to keep this fix scoped to the confirmed
        correctness bug.

        CRITICAL: raises on failure, same as `update_rs_percentiles()` - an inconsistent value_
        score/composite_score is a live-trading-relevant correctness issue, not just Phase 7
        display noise.
        """
        try:
            with DatabaseContext("write") as cur:
                cur.execute("""
                    SELECT ss.symbol, ss.value_score, ss.composite_score, ss.risk_score,
                           ss.quality_score, ss.growth_score, ss.momentum_score,
                           vm.pe_ratio, vm.pb_ratio, vm.ps_ratio, vm.forward_pe,
                           vm.dividend_yield,
                           vm.pe_ratio_unavailable_reason, vm.forward_pe_unavailable_reason,
                           ss.components
                    FROM stock_scores ss
                    JOIN value_metrics vm ON vm.symbol = ss.symbol
                    WHERE ss.value_score IS NOT NULL
                      AND COALESCE(vm.data_unavailable, false) = false
                """)
                rows = cur.fetchall()

            if not rows:
                logger.warning(
                    "[STOCK_SCORES] update_value_multiples_percentiles: no eligible rows found "
                    "(value_score IS NOT NULL joined to value_metrics) - skipping, nothing to correct."
                )
                return

            pe_raw: dict[str, float] = {}
            pb_raw: dict[str, float] = {}
            ps_raw: dict[str, float] = {}
            fwd_pe_raw: dict[str, float] = {}
            # unprofitable_symbols/negative_fwd_symbols: floored at percentile 0.0 directly
            # below (not run through _percent_rank_cheap_high) - see _score_value's
            # "UNPROFITABLE-COMPANY FLOOR ADDED 2026-08-28" docstring note for why a floor
            # (not exclusion) is the theoretically correct treatment here.
            unprofitable_symbols: set[str] = set()
            negative_fwd_symbols: set[str] = set()
            for row in rows:
                symbol, pe, pb, ps, fwd_pe = row[0], row[7], row[8], row[9], row[10]
                pe_reason, fwd_pe_reason = row[12], row[13]
                if pe is not None and float(pe) > 0:
                    pe_raw[symbol] = float(pe)
                elif pe_reason == "unprofitable_stock":
                    unprofitable_symbols.add(symbol)
                if pb is not None and float(pb) > 0:
                    pb_raw[symbol] = float(pb)
                if ps is not None and float(ps) > 0:
                    ps_raw[symbol] = float(ps)
                if fwd_pe is not None and float(fwd_pe) > 0:
                    fwd_pe_raw[symbol] = float(fwd_pe)
                elif fwd_pe_reason == "negative_forward_eps":
                    negative_fwd_symbols.add(symbol)

            pe_pct = self._percent_rank_cheap_high(pe_raw)
            pb_pct = self._percent_rank_cheap_high(pb_raw)
            ps_pct = self._percent_rank_cheap_high(ps_raw)
            fwd_pe_pct = self._percent_rank_cheap_high(fwd_pe_raw)
            for symbol in unprofitable_symbols:
                pe_pct[symbol] = 0.0
            for symbol in negative_fwd_symbols:
                fwd_pe_pct[symbol] = 0.0
            logger.info(
                f"[STOCK_SCORES] Value multiples percentile universe: "
                f"P/E {len(pe_pct)} ({len(unprofitable_symbols)} floored unprofitable), "
                f"P/B {len(pb_pct)}, P/S {len(ps_pct)}, "
                f"Forward P/E {len(fwd_pe_pct)} ({len(negative_fwd_symbols)} floored negative-forecast) symbols"
            )

            updates: list[tuple[str, float, float, str | None]] = []
            for row in rows:
                symbol, value_score_old, composite_score_old, risk_score = row[0], row[1], row[2], row[3]
                quality_score, growth_score, momentum_score = row[4], row[5], row[6]
                pe, pb, ps, fwd_pe, dividend_yield = row[7], row[8], row[9], row[10], row[11]
                pe_reason, fwd_pe_reason = row[12], row[13]
                components_old = row[14]
                value_score_old = float(value_score_old)
                composite_score_old = float(composite_score_old)

                # Pure recompute of value_score from the raw stored inputs - percentile rank
                # for PE/PB/PS/forward_pe, dividend's own unchanged curve score (_score_value's
                # own formula, see that method) - value_score_old is read above only to detect
                # whether anything changed, never as an input to the new value. See "BUG FOUND
                # + FIXED 2026-08-31" docstring note above for why this replaced the prior
                # additive-delta-on-a-mutable-column design.
                # EQUAL-WEIGHTED 2026-09-01 (see _score_value's own matching note - "lets get
                # the weightings more normal... is that what the industry players set these at
                # too?"). PE/PB/PS now equal at 27% each (was 12/41/35, data-driven skew toward
                # PB/PS) - matches AQR/practitioner convention of averaging core value ratios
                # roughly equally rather than in-sample-optimized weights. Forward P/E raised
                # 4%->9%, Dividend Yield raised 8%->10% (both stay smaller satellite weights,
                # not equal to the 3 core multiples).
                components: list[tuple[float, float]] = []
                if pe is not None and float(pe) > 0:
                    components.append((pe_pct[symbol], 0.27))
                elif pe_reason == "unprofitable_stock":
                    components.append((0.0, 0.27))
                if pb is not None and float(pb) > 0:
                    components.append((pb_pct[symbol], 0.27))
                if ps is not None and float(ps) > 0:
                    components.append((ps_pct[symbol], 0.27))
                if fwd_pe is not None and float(fwd_pe) > 0:
                    components.append((fwd_pe_pct[symbol], 0.09))
                elif fwd_pe_reason == "negative_forward_eps":
                    components.append((0.0, 0.09))
                # FIXED 2026-08-31 (same fix, same reasoning as _score_value's own dividend
                # block above - value_metrics.dividend_yield is a real, already-computed 0.0
                # for non-payers, never NULL, so a `> 0` gate wrongly reweighted this term away
                # for 56% of the universe instead of scoring the real 0% floor).
                # TRIMMED 11%->8% 2026-08-31, RAISED 8%->10% 2026-09-01 (equal-weight reweight
                # above) - weak evidence, kept at user directive, sized as a satellite weight.
                if dividend_yield is not None:
                    div = min(float(dividend_yield) * 100, 6)  # decimal -> percent, cap 6%
                    div_score = min(100, div * 16.7)
                    components.append((div_score, 0.10))

                total_weight = sum(w for _, w in components)
                if total_weight <= 0:
                    # Defensive only - can't happen if value_score is a real float (it required
                    # total_weight > 0 to compute in the first place), but never divide by zero.
                    continue

                value_score_new = round(max(0.0, min(100.0, sum(v * w for v, w in components) / total_weight)), 2)

                # Pure recompute of composite_score from the 5 pillar scores as they currently
                # stand in stock_scores (quality/growth/risk/momentum are untouched by this
                # pass - only value_score changed above), mirroring _score_value's own caller
                # (no weight redistribution for a missing pillar - GOVERNANCE rule, same as
                # Pass 1) instead of patching composite_score_old by a delta.
                risk_score_float = float(risk_score) if risk_score is not None else None
                weights = _value_risk_adjusted_weights(risk_score_float)
                composite_val = 0.0
                for pillar_name, pillar_score in (
                    ("quality", quality_score),
                    ("growth", growth_score),
                    ("value", value_score_new),
                    ("risk", risk_score),
                    ("momentum", momentum_score),
                ):
                    if pillar_score is not None:
                        composite_val += float(pillar_score) * weights[pillar_name]
                composite_score_new = round(max(0.0, min(100.0, composite_val)), 2)

                if value_score_new != value_score_old or composite_score_new != composite_score_old:
                    # BUG FIX 2026-08-29 (goal-mode composite-score validation pass): components
                    # must be kept in sync with the corrected value_score here, or it silently
                    # drifts from the real composite_score math - see
                    # _components_with_corrected_value's own docstring for the full evidence.
                    components_json = self._components_with_corrected_value(components_old, value_score_new)
                    updates.append((symbol, value_score_new, composite_score_new, components_json))

            if not updates:
                logger.info(
                    "[STOCK_SCORES] Value multiples percentile pass: no symbol's value_score/"
                    "composite_score changed (expected on a repeat run with unchanged inputs - "
                    "this pass is now idempotent, see its 'BUG FOUND + FIXED 2026-08-31' note)."
                )
                return

            with DatabaseContext("write") as cur:
                execute_values(
                    cur,
                    """
                    UPDATE stock_scores AS ss
                    SET value_score = v.value_score,
                        composite_score = v.composite_score,
                        components = v.components::jsonb,
                        updated_at = CURRENT_TIMESTAMP
                    FROM (VALUES %s) AS v(symbol, value_score, composite_score, components)
                    WHERE ss.symbol = v.symbol
                    """,
                    updates,
                    template="(%s, %s, %s, %s)",
                )
            logger.info(
                f"[STOCK_SCORES] Value multiples cross-sectional percentile pass corrected "
                f"{len(updates)}/{len(rows)} symbols' value_score/composite_score (post_run completed)"
            )
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            error_msg = f"Value multiples percentile batch update failed - stock scores cannot be finalized: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e

    # update_size_percentiles() REMOVED 2026-08-28 (Size retired as a composite pillar - see
    # BASE_PILLAR_WEIGHTS for the full evidence trail).

    def snapshot_score_history(self) -> None:
        """Batch pass: snapshot today's stock_scores into stock_scores_history.

        Must run after update_rs_percentiles() so the snapshot includes the finalized
        rs_percentile from this same run, not a stale value from the prior run.

        One row per (symbol, score_date): re-running post_run() on the same calendar day
        (e.g. a retry) updates that day's snapshot in place rather than appending a
        duplicate, so history stays one data point per trading day regardless of how many
        times the loader runs that day.

        composite_rank is computed once here (not at read time) so a stock's historical
        rank reflects the universe actually scored that day, not today's universe size.

        CRITICAL: Raises on failure, same as update_rs_percentiles() - a broken snapshot
        pass should be visible, not silently swallowed.
        """
        try:
            with DatabaseContext("write") as cur:
                cur.execute("""
                    INSERT INTO stock_scores_history (
                        symbol, score_date, composite_score, composite_rank,
                        momentum_score, quality_score, growth_score, value_score,
                        risk_score, rs_percentile,
                        data_completeness, updated_at
                    )
                    SELECT
                        symbol,
                        CURRENT_DATE,
                        composite_score,
                        RANK() OVER (ORDER BY composite_score DESC NULLS LAST) AS composite_rank,
                        momentum_score, quality_score, growth_score, value_score,
                        risk_score, rs_percentile,
                        data_completeness, CURRENT_TIMESTAMP
                    FROM stock_scores
                    WHERE data_unavailable IS NOT TRUE AND composite_score IS NOT NULL
                    ON CONFLICT (symbol, score_date) DO UPDATE SET
                        composite_score = EXCLUDED.composite_score,
                        composite_rank = EXCLUDED.composite_rank,
                        momentum_score = EXCLUDED.momentum_score,
                        quality_score = EXCLUDED.quality_score,
                        growth_score = EXCLUDED.growth_score,
                        value_score = EXCLUDED.value_score,
                        risk_score = EXCLUDED.risk_score,
                        rs_percentile = EXCLUDED.rs_percentile,
                        data_completeness = EXCLUDED.data_completeness,
                        updated_at = CURRENT_TIMESTAMP
                """)
                snapshotted = cur.rowcount
            logger.info(f"Score history snapshot written for {snapshotted} symbols (post_run completed)")
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            error_msg = f"Score history snapshot failed: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e


if __name__ == "__main__":
    sys.exit(run_loader(StockScoresLoader))
