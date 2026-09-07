"""Composite pillar weights and the Value/Risk interaction adjustment, extracted from
load_stock_scores.py (2026-09-05, file-size-ratchet bloaters-decomposition split).

Moved verbatim - no behavior change. Lives in its own leaf module (no dependency on
load_stock_scores.py or any stock_scores/*.py mixin) specifically so both the loader itself
(_compute_stock_score) and ValueMetricsMixin.update_value_multiples_percentiles (a separate
mixin module) can import BASE_PILLAR_WEIGHTS / _value_risk_adjusted_weights without a circular
import - see loader_comment_bloat_compaction / vqg_and_stock_scores_dead_split_files_deleted in
memory for why a naive split of this file previously failed.

Re-exported from loaders.load_stock_scores for backward compatibility - existing consumers
(algo/research/*.py, dashboard/panels/scores.py, several tests) import these names directly
from loaders.load_stock_scores and must keep working unchanged.
"""

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
# ============================================================================================
# WEIGHT-REVISION GOVERNANCE POLICY (added 2026-09-07, goal session: "find all the stupid
# shit... figure out the best right way"). Read this before changing any weight below.
#
# The docstring history above (and value_score.py's own, longer one) is a real audit finding,
# not just color commentary: this file's weights were repeatedly changed, tested, reversed, and
# re-reversed WITHIN THE SAME SESSION, sometimes multiple times in one day, each time citing a
# fresh re-run of the same backtest that contradicted the immediately-prior "robust,
# independently re-verified" conclusion (see e.g. "PE-vs-PB/PS RANKING - REVERSED", then
# "INDEPENDENT RE-VERIFICATION", then reversed AGAIN in value_score.py the same day). Repeatedly
# re-mining the same in-sample window until a different number comes out is the textbook setup
# for overfitting to noise, not evidence-based iteration - re-verified numbers were only ever
# re-verified against the SAME data already used to motivate the change.
#
# This is exactly the discipline institutional multi-factor shops (Barra/Axioma/MSCI/AQR)
# enforce and this repo did not: factor weights get re-estimated on a FIXED SCHEDULE (typically
# quarterly/annually), never same-session, and validated with a TRUE held-out period that was
# never touched during fitting - not an overlapping half-split re-used for both "discovery" and
# "confirmation" the way multiple passes above did. See algo/research/
# barra_style_neutralized_composite_20260907.py for a worked example of the honest version of
# this: fit period 2017-2021, holdout 2022-2026, holdout NEVER touched while iterating on the
# method.
#
# GOING FORWARD:
#   1. A weight in this file may only be changed based on a test that reports BOTH a fit-period
#      AND a genuinely disjoint, never-previously-examined holdout-period result - not a
#      same-window half-split re-used across multiple same-day passes.
#   2. If a proposed change doesn't clear this repo's own stated bar (|t|>=2, same sign, in
#      both periods) OR the improvement is marginal (a few tenths of a t-stat) relative to the
#      noise level already documented in this file's own history (pre-2020 sub-periods are
#      consistently the noisiest), DO NOT ship it - document the finding and leave the
#      production weight alone, the same restraint already correctly applied to margin_of_safety
#      and dividend_yield's own "kept, not acted on further" verdicts above.
#   3. Don't re-run the identical test a second time in the same session hoping for a different
#      number "to be sure" - if the first honest run doesn't clear the bar, that IS the answer,
#      not a reason to keep trying until it does.
#   4. Routine hand-calibrated fixes to a SCORING CURVE (not a pillar weight) - e.g. the
#      2026-09-07 bank/insurer/utility ROA/ROCE/debt-to-equity curves in
#      loaders/helpers/vqg_quality.py - are lower-stakes than a top-level pillar weight change
#      but still deserve at minimum a live-distribution sanity check (does the new curve's
#      breakpoint land near the REAL cross-sectional median/percentile for that peer group, not
#      just "looks right" on a handful of spot-checked symbols) before landing, per this same
#      session's own bank ROA calibration check (median bank ROA 1.04% vs. the new curve's
#      1.0%->75 breakpoint - that's how you'd catch an overly generous or overly harsh curve
#      BEFORE it ships, not after a leaderboard looks wrong).
# ============================================================================================
BASE_PILLAR_WEIGHTS: dict[str, float] = {
    "quality": 0.20,
    "growth": 0.24,
    "value": 0.27,
    "risk": 0.19,
    "momentum": 0.10,
}
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
