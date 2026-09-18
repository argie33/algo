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
#   5. MULTIPLE-COMPARISONS CORRECTION (added 2026-09-12, see
#      multiple_hypothesis_testing_no_fdr_correction_20260912 in memory). Rule #2's |t|>=2 bar
#      is a PER-TEST bar - fine for a single pre-registered hypothesis, but this repo's
#      fama_macbeth_*.py family has tested ~65 candidate factors total across its history
#      (Growth 11, Value 8, Quality 22, Quality-trend 5, Momentum 8, Price 8, Positioning 1,
#      Liquidity 2), each judged individually at |t|>=2 (~p<0.05) with zero correction for how
#      many were tried. Testing 65 independent candidates at p<0.05 produces ~3 "significant"
#      hits by chance alone even if none of them are real factors - the volume of testing is
#      itself a source of false positives, separate from and in addition to the same-session
#      re-testing this policy already bans in rule #3.
#      GOING FORWARD: any screen that tests MORE THAN ONE candidate column in the same pass
#      (a univariate sweep over N columns, a curve/interaction search, an "extended candidate
#      list" like QUALITY_FACTOR_COLS's extended/altman/roic/new/cash-quality batches) MUST
#      run algo.research.fama_macbeth_price_factors.benjamini_hochberg_fdr(t_stats, n_months)
#      across that whole candidate family and report which survive FDR q<=0.10, not just which
#      individually clear |t|>=2. A candidate that clears |t|>=2 alone but fails the FDR
#      correction for its batch has NOT cleared this repo's bar - do not promote it to a
#      pillar/component weight on the strength of the uncorrected number. This does not
#      retroactively invalidate weights already live (see the file's own history above for
#      what evidence backed each); it applies to every new candidate screen from here on.
#   6. NO CIRCULAR FORWARD-RETURN VALIDATION FOR PRICE-TOUCHED INPUTS (added 2026-09-12, see
#      forward_return_validation_methodology_circular_for_price_derived_pillars_20260912 in
#      memory). stock_scores/value_metrics/quality_metrics/momentum_metrics are single-row
#      snapshots (no history - COUNT(DISTINCT date) GROUP BY symbol returns 1 for every symbol).
#      "Today's score vs. this symbol's own trailing realized return" is NOT a valid earned/
#      artifact test for ANY input whose current value is itself a function of recent price
#      action - Momentum by construction, but also P/E, P/B, dividend_yield, and Risk's
#      volatility legs (any ratio where the price side just moved). Comparing "this went up" to
#      "this has been going up" proves nothing; it is not a weaker test, it is not a test at all.
#      GOING FORWARD: any "is this concentration/inversion real or a scoring artifact" question
#      touching a price-derived input MUST use a genuine point-in-time panel reconstructed from
#      price_daily/annual_income_statement/annual_balance_sheet with real calendar-FYE + lag
#      handling - the fama_macbeth_quality_factors.py / fama_macbeth_value_factors.py pattern,
#      extended with an --industries filter where the question is sub-industry-specific (see
#      industry_conditional_pillar_signal_banks_insurers_reits_compared_20260912) - never the
#      snapshot-vs-trailing-return shortcut. Conclusions already reached via the circular method
#      are UNCONFIRMED, not disproven, and must be redone this way before being trusted for a
#      production weight decision: financial_services_pillar_concentration_deserved_not_artifact_
#      20260911, reit_risk_pillar_concentration_not_fixable_by_sector_relative_20260911, and
#      insurance_community_bank_subcluster_earned_gate_binds_20260912 all rest on this method and
#      are open again until redone.
# ============================================================================================
# SECTOR-NEUTRALITY GOVERNANCE POLICY (added 2026-09-13, goal session: composite-score
# structural audit - see [[composite_score_structural_audit_plan_20260913]] in memory). This is
# the same-spirit companion to the WEIGHT-REVISION GOVERNANCE POLICY above, for a DIFFERENT
# question this file's own history shows was decided ad hoc, pillar-by-pillar, at different
# times, with different evidence standards: should a pillar's raw inputs be transformed via a
# SECTOR-RELATIVE winsorize+z-score (`loaders/helpers/factor_normalization.py`'s
# `sector_neutral_zscore`), or an absolute/universe-wide one?
#
# The pattern that triggered this policy: Risk's vol/max_drawdown were made universe-wide on
# 2026-09-13 on the argument that the low-volatility anomaly (Ang et al. 2006; Frazzini &
# Pedersen 2014) is harvested on an absolute basis in the published literature - a real argument,
# but never tested against this repo's OWN data before being acted on. Hours later, a fresh
# non-circular test (`algo/research/fama_macbeth_price_factors.py --industries
# banks|insurers|reits`) found zero robust forward-return edge for vol/beta/max_dd in exactly the
# 3 industries that argument was meant to protect - see risk_scoring.py's own module docstring
# and [[risk_pillar_sector_neutralized_20260913]] for the full reversal. The literature-citation
# argument alone was not sufficient evidence; a live re-test was.
#
# GOING FORWARD: a pillar/component's sector-neutrality classification (sector-relative vs.
# absolute/universe-wide) may only be set or changed based on a NON-CIRCULAR, point-in-time panel
# test - the fama_macbeth_quality_factors.py / fama_macbeth_value_factors.py /
# fama_macbeth_price_factors.py pattern (real historical price_daily/annual_income_statement/
# annual_balance_sheet reconstruction, never the single-row-stock_scores-snapshot-vs-trailing-
# return shortcut banned by rule #6 of the weight-revision policy above), using an `--industries`
# filter for any sub-industry-specific concentration question, with the SAME era-robustness
# (4-block, not a single 50/50 split) and FDR bar already mandated there. A plausible-sounding
# academic citation is a reason to RUN that test, not a substitute for running it. Re-run
# whenever a prior sector-neutrality decision predates this bar, and always note the
# survivorship-bias caveat (`SURVIVORSHIP_BIAS_CAVEAT` in fama_macbeth_price_factors.py) on the
# result - it limits confidence in every such test, not just weight decisions.
#
# SECOND VIOLATION FOUND AND FIXED 2026-09-17 (factor-purity follow-up, user: "where we
# inaccurately mixing industry things to a point where it doesn't make sense"): Growth
# (growth_scoring.py's update_growth_sector_neutral_scores) was STILL sector-relative, and had
# never actually cleared this policy's own bar - it was never independently tested, sector-
# relative or otherwise. It was built 2026-09-08 by copying Quality's THEN-current
# sector-relative implementation (a real precedent at the time), but Quality was itself REBUILT
# to a cited, universe-wide MSCI z-score on 2026-09-16 - Growth's own construction was never
# revisited alongside it, so it kept inheriting a rationale that had since been retracted at the
# source. A later docstring pass papered over the gap by claiming universe-wide-vs-sector-relative
# "matches MSCI's real Growth-trend methodology (this file's own top-of-file citation)" - false on
# inspection: that citation (GROWTH_SCORE_FIELDS_SUPERSEDED_NOTE) is entirely about which 4
# descriptors match MSCI GIMIVG/Barra EGRO, and says nothing about sector relativity at all. This
# is the exact failure mode this policy exists to catch - a plausible-sounding citation standing
# in for an actual test - just one level removed (citing a DIFFERENT document's unrelated finding,
# rather than citing the right document's own literature argument, the way Risk's original mistake
# did). Reverted to `universe_wide_zscore`, matching Quality/Momentum/Risk's own converged
# position - see update_growth_sector_neutral_scores()'s own "REVERSED TO UNIVERSE-WIDE" docstring
# note for the full detail. Value remains the one deliberate exception (sector-relativized, but
# only at the COMPOSITE stage, per MSCI Enhanced Value Appendix II - a different, cited, real
# document describing a different index family from the other four pillars' plain style indexes).
# ============================================================================================
# TWO-LAYER VALIDATION POLICY (added 2026-09-15, user directive - supersedes the implicit
# assumption behind the SECTOR-NEUTRALITY GOVERNANCE POLICY above and every pillar-level
# Fama-MacBeth/IC rejection in this file's history that used a PILLAR's own forward-return IC
# as the bar for a PILLAR-level construction choice, e.g.
# momentum_pillar_sector_relative_mom_12_1_rejected_20260911). Two different questions, two
# different tests, explicitly stated by the user so this stops being re-litigated ad hoc:
#
#   PILLAR level (quality_score/growth_score/value_score/risk_score/momentum_score): the job
#   is to accurately MEASURE that factor, the same way real institutional single-factor
#   products/indexes measure it (MSCI/Barra/AQR published methodology). Validate a pillar
#   construction choice against fidelity to the real, sourced factor definition - NOT whether
#   it individually predicts forward returns. A pillar with zero standalone IC is not
#   automatically wrong; a pillar that doesn't resemble how the real factor is actually defined
#   IS wrong, regardless of its own IC.
#   EXAMPLE, KEPT CORRECTED (2026-09-16 factor-purity sweep): this policy block originally cited
#   "MTUM's real underlying index... z-scores momentum WITHIN each GICS sector" as its
#   illustrative example - that claim was itself a real-money-readiness-pass finding from
#   2026-09-15 that got REVERSED the same day (live-verified against fresh MTUM daily holdings:
#   sector-relative cap-neutral rank correlation 0.235 vs. universe-wide 0.558 - see
#   momentum_scoring.py's own history) and independently RE-CONFIRMED 2026-09-16 by fetching
#   MSCI's real Momentum Indexes Methodology PDF directly (Aug 2021, Section 2.2): momentum is
#   z-scored ONCE, UNIVERSE-WIDE within the Parent Index - no sector grouping anywhere in the
#   document. This policy block's own worked example was left citing the pre-reversal claim
#   until now, the identical "docstring lied, code was already right" gap already found once
#   this session for Value - fixed here rather than left to mislead a future reader who trusts
#   this file's own precedent-setting example over the pillar's own (correct) live code.
#
#   COMPOSITE level (composite_score): the job is to identify the best actual stock
#   opportunity. Validate composite-level changes (pillar weights, cross-pillar interactions
#   like the Value x Risk adjustment below) against forward-return prediction (IC,
#   Fama-MacBeth) - this is where predictive testing belongs.
#
# Practical effect: a pillar-level construction change should still be checked for whether it
# measurably hurts COMPOSITE-level IC before shipping (the composite is still the thing that
# has to work), but "this pillar's own solo IC got worse" is no longer by itself a reason to
# reject a pillar construction that's more faithful to the real factor definition.
# ============================================================================================
# UNIFORM EQUAL-WEIGHT PRINCIPLE (2026-09-11, user directive: the backtest/Fama-MacBeth evidence
# behind every non-Growth pillar's weights is the same contaminated-data family this module's own
# history above already documents for the composite level (imputed vs. complete-case regimes
# disagree, missingness is non-random, "no pillar robustly clears the bar" under the honest
# methodology) - rather than re-litigate each pillar's weights in isolation again, every level of
# the scoring hierarchy (component->pillar, pillar->composite) now uses a single uniform rule:
# equal-weight whichever inputs are available. No magnitude/t-stat/backtest-derived differential
# weighting anywhere. This extends what Growth (1/12 each) and Value's PE/PB/PS core (27/27/27)
# already did on prior user override - not a new philosophy, just applied consistently instead of
# pillar-by-pillar. The extensive weight-revision history above is kept as the audit trail of what
# was tried and why it was abandoned, not because it still justifies today's live weights.
# THIS IS CLOSED (added 2026-09-16, after a stale un-merged worktree from 2026-09-11 -
# .claude/worktrees/equal-weight-pillar-refactor, deleted 2026-09-16 - was found still sitting
# on disk reintroducing IC-tuned differential component weights, the exact pattern this policy
# exists to stop). Equal-weight is not a placeholder pending a better idea - it is the decision,
# reached after this file's own extensive multi-week churn history above and an explicit user
# directive to stop it. Do NOT open a new worktree/branch to re-derive per-component or
# per-pillar weights from a backtest "to see if equal-weight still holds" - it will not produce
# a materially different, non-noise answer than the history above already found, and an
# uncommitted or unmerged branch that disagrees with this file is not a pending decision, it is
# an artifact to delete. Re-opening this requires the SAME bar every rule above already sets
# (disjoint fit/holdout, era-robust, FDR-corrected if multi-candidate) AND an explicit new user
# directive citing genuinely new data - not a session's own initiative. If you build a
# throwaway/investigative branch or worktree to test a candidate against this file, delete it
# (or merge it, if it clears the bar) before ending the task that created it - do not leave it
# for a future session to rediscover. See scripts/check_worktree_health.py.
# GROWTH: VISIBLE, NOT DOUBLE-WEIGHTED (decided 2026-09-17, explicit user choice among 3
# options presented live - see /goal transcript: "Growth visible, not double-weighted" over (a)
# restoring Growth as a 5th equal-weighted pillar with Quality's QMJ Growth leg dropped to
# compensate, or (b) keeping both and accepting the overlap). growth_score stays fully computed,
# stored, and displayed (GrowthScoringMixin/_score_growth, update_growth_sector_neutral_scores,
# the Growth tab in StockScoreAccordion.jsx - real content, not a stub) - it is just NOT one of
# BASE_PILLAR_WEIGHTS' own keys, because its real predictive content already has a home in
# Quality's own QMJ Growth sub-score (Asness/Frazzini/Pedersen 2019 "Quality Minus Junk," Table
# 2: 5-year change in each Profitability-leg measure - see vqg_quality_batch.py's
# update_quality_sector_neutral_scores). Also counting a second, separately-weighted top-level
# Growth pillar in composite_score would double-weight the same underlying "growth-ness" signal
# (correlated, not identical measures, but not independent either) - this was the user's own
# explicit reasoning for this choice, not an AQR-purism argument alone.
# NOTE: this exact dict flip-flopped between this 4-key form and a 5-key growth-included form
# multiple times on 2026-09-17 because more than one concurrent session was editing this file at
# once - if you find this dict disagreeing with the "GROWTH: VISIBLE, NOT DOUBLE-WEIGHTED" note
# above, or vice versa, treat that as a live collision to resolve (check the other session's
# state, don't just silently pick one), not as this comment being stale.
# Every composite-recompute call site (this file, load_stock_scores.py, quality_scoring.py,
# momentum_scoring.py, risk_scoring.py, value_metrics.py, growth_scoring.py's OWN pass,
# algo/monitoring/data_patrol/checks/composite_score_reconciliation.py) must exclude "growth"
# from BASE_PILLAR_WEIGHTS-keyed lookups.
# ============================================================================================
# ABOVE DECISION SUPERSEDED, SAME DAY (2026-09-17, explicit user directive: "we need to get the
# growth back that one got dropped"). The user reversed the "GROWTH: VISIBLE, NOT DOUBLE-WEIGHTED"
# choice directly above and picked option (a) from that same 3-option menu instead: Growth
# restored as a 5th equal-weighted top-level pillar (quality/value/risk/momentum/growth, 0.20
# each), with Quality's QMJ Growth leg DROPPED from vqg_quality_batch.py's
# update_quality_sector_neutral_scores (at the time, a 3-leg Profitability/Safety/Payout
# composite) so growth-ness is only counted once across the composite instead of twice.
# growth_score itself (GrowthScoringMixin/_score_growth, update_growth_sector_neutral_scores) is
# unchanged - it was already fully computed; it is now also one of the weighted pillars again.
# Every "must exclude growth from BASE_PILLAR_WEIGHTS-keyed lookups" call site listed in the
# paragraph above this one no longer applies - growth is back in the loop at every one of those
# call sites. NOTE: the "Quality's QMJ Growth leg DROPPED" detail above is now itself superseded
# by the MSCI-REVERSION note directly below - Quality no longer uses QMJ's leg structure AT ALL,
# so there is no QMJ Growth leg left to drop; this paragraph is kept for the audit trail of why
# Growth came back, not as a description of Quality's current construction.
# ============================================================================================
# MSCI-REVERSION FOR VALUE/MOMENTUM/QUALITY, SAME DAY (2026-09-17, explicit user decision after
# a fresh session-initiated audit). Earlier the same day, a separate "factor-purity pivot" (user
# directive: "we are not using industry standard AQR yet for all the factors... get rid of the
# msci and all this other shit", commit 4beaf7f1c) had replaced:
#   - Value: MSCI Enhanced Value's 3-leg blend -> AQR's single book-to-market measure
#   - Momentum: MSCI's risk-adjusted 6m+12-1 blend -> AQR's single raw 12-1 skip-month return
#   - Quality: MSCI's 3-variable Quality Index (ROE/Debt-to-Equity/Earnings-Variability) ->
#     AQR's Quality Minus Junk (QMJ) 4-leg (later 3-leg, after Growth was restored above)
#     Profitability/Safety/Payout composite
# An independent audit (6 parallel sub-agents, each re-fetching and reading the real MSCI/AQR
# primary-source documents rather than trusting this file's own docstrings) confirmed the pivot
# had genuinely happened as described - not a docstring inaccuracy - and surfaced it as a direct
# conflict with the user's later, explicit request to "make sure they are perfectly implemented
# the MSCI style for all the factors ... showing the right MSCI style with the market cap
# weighting". Given that direct choice, the user chose MSCI fidelity over AQR-purism for these
# 3 pillars: Value, Momentum, and Quality were all REVERTED to their real, pre-pivot MSCI
# constructions (see value_metrics.py's update_value_multiples_percentiles(), momentum_scoring.py's
# update_momentum_sector_relative_mom_12_1()/module docstring, and vqg_quality_batch.py's
# update_quality_sector_neutral_scores() for each pillar's own restored construction and
# citation). Risk was NOT part of this reversion - Risk was never MSCI to begin with (it's
# Frazzini-Pedersen Betting-Against-Beta either way, same audit confirmed this pillar's AQR
# construction is a legitimate, correctly-cited implementation, independent of the MSCI question)
# - so Risk stays on its 2026-09-17 AQR beta_bab construction. Growth was also unaffected - it
# was never touched by the AQR pivot and remains MSCI GIMIVG-style (confirmed correct by the same
# audit). market_caps (free-float market-cap-weighted z-scoring, matching MSCI's real z-score
# formula) was wired into all 3 reverted pillars' universe_wide_zscore calls as part of this same
# pass - see factor_normalization.py's own docstring for the shared-engine side of that fix.
# BASE_PILLAR_WEIGHTS itself (5 keys, 0.20 each) is UNCHANGED by this reversion - this note is
# about pillar CONSTRUCTION (how each score is computed), not pillar WEIGHT (how much each score
# counts toward composite_score).
# ============================================================================================
BASE_PILLAR_WEIGHTS: dict[str, float] = {
    "quality": 0.20,
    "value": 0.20,
    "risk": 0.20,
    "momentum": 0.20,
    "growth": 0.20,
}
# VALUE x RISK INTERACTION - REMOVED ENTIRELY 2026-09-15 (user directive: "get rid of all the
# extra shit beyond the barra and the industry guys" - real Barra-style multi-factor models
# combine factor exposures linearly with fixed weights; they don't shift one factor's weight
# based on another factor's own score for the same symbol via a hand-built interaction
# function). This constant/function had already been RETIRED to a permanent no-op on
# 2026-09-11 (see git history) - always returned BASE_PILLAR_WEIGHTS unmodified regardless of
# risk_score. Removing the dead indirection entirely rather than leaving inert machinery in
# place; every call site now uses BASE_PILLAR_WEIGHTS directly. See git history for the full
# evidence trail (value_proxy x stability_proxy interaction sweep, its later retirement) if a
# future session wants to revisit a real interaction term - that would need to be a genuine
# risk-model construct (e.g. a factor-covariance term), not an ad hoc linear weight shift.
#
# OLD DOCSTRING (kept for archaeology only, describes removed code):
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
# RETIRED 2026-09-11 (same uniform-equal-weight directive as BASE_PILLAR_WEIGHTS above): this
# interaction was itself a differential/conditional weighting device, and the sweep that
# justified it (cross_pillar_interaction_sweep_20260828.py) is the same contaminated-data family
# as the composite-level FM work. Left at 0.0 (not deleted) so any stale caller doing arithmetic
# with this constant is inert rather than broken. _value_risk_adjusted_weights below now always
# returns BASE_PILLAR_WEIGHTS unmodified - kept as a function (not inlined at call sites) so
# load_stock_scores.py/growth_scoring.py don't need their own call-site changes.

# INVESTABILITY FLOOR (RETIRED as a market-cap gate 2026-09-15, user directive - corrects the
# 2026-09-15 same-day API-layer change that kept BOTH a $300M cap floor AND a new liquidity
# screen "alongside, not instead of" each other, per that change's own docstring. That was
# self-contradictory on its own evidence: this repo's own research already established real
# IBD screens (IBD 50) span small/mid/large-cap by design and have NO market-cap floor at all -
# their real screens are liquidity-based (minimum share price, minimum average daily dollar
# volume), see lambda/api/routes/scores.py's own updated comment. A $300M cap floor is
# structurally the wrong tool for an IBD-style system regardless of what threshold it uses, not
# just the wrong NUMBER - keeping it "because it doesn't gate large-caps" missed that a real
# IBD-style screen doesn't gate on cap size in either direction.
#
# DELETED 2026-09-15 (dead-code sweep, "get rid of the extra shit beyond Barra and the
# industry guys" directive): the comment that used to sit here claiming this constant was "kept
# ONLY as the tilt-formula input for update_market_cap_tilted_weights" was itself stale -
# market_cap_tilt.py's update_market_cap_tilted_weights reads `vm.market_cap` straight from the
# DB and never touched this constant or self._min_investable_market_cap. A repo-wide grep for
# `min_investable_market_cap` found exactly one file referencing it at all -
# loaders/load_stock_scores.py, where it was read from algo_config/defaulted into
# self._min_investable_market_cap and then never read again anywhere - fully dead, not merely
# misleadingly named, so both DEFAULT_MIN_INVESTABLE_MARKET_CAP and self._min_investable_
# market_cap were removed outright rather than left as inert machinery. See
# DEFAULT_MIN_STOCK_PRICE/DEFAULT_MIN_ADV_DOLLARS/LIQUIDITY_FLOOR_JOIN_SQL below for the
# liquidity-based floor that replaced it everywhere a batch pass gates its z-score/percentile
# peer population on market_cap.

# LIQUIDITY-BASED INVESTABILITY FLOOR (added 2026-09-15, replaces DEFAULT_MIN_INVESTABLE_MARKET_CAP
# as the eligibility gate for every pillar batch pass's z-score/percentile peer population - see
# DEFAULT_MIN_INVESTABLE_MARKET_CAP's own docstring above for why). Same real thresholds already
# governing live trade EXECUTION (algo_config min_stock_price/min_adv_dollars,
# algo/risk/liquidity_checks.py) and the API layer's own IBD-style screen
# (lambda/api/routes/scores_handlers/stock_scores.py) - one number, read once
# (`_prepare_batch_context` -> self._min_stock_price/self._min_adv_dollars), not hand-copied per
# pillar file. These two constants are ONLY the fallback for a missing algo_config row or a
# batch-pass method called without `_prepare_batch_context` having run (isolated unit tests) -
# same convention as every other fallback constant in this file.
DEFAULT_MIN_STOCK_PRICE = 5.0
DEFAULT_MIN_ADV_DOLLARS = 500_000.0

# Shared liquidity-floor JOIN fragment - every pillar batch pass's population query joins
# `stock_scores ss` (or a CTE selecting off it), so `ss.symbol` is the one consistent join key
# across all 6 call sites (vqg_quality_batch.py, growth_scoring.py, value_metrics.py,
# risk_scoring.py, momentum_scoring.py, market_cap_tilt.py) - unlike the API layer's own copy of
# this same fragment (lambda/api/routes/scores_handlers/stock_scores.py), which joins off `sc`.
# 45-calendar-day / last-20-real-trading-day window matches every other avg_dollar_volume_20d
# computation already live in this codebase (risk_scoring.py's own pre-existing `liquidity` CTE,
# the API layer's copy) - not a new convention invented here.
LIQUIDITY_FLOOR_JOIN_SQL = """
                    JOIN (
                        SELECT symbol,
                               AVG(volume * close) AS avg_dollar_volume_20d,
                               (ARRAY_AGG(close ORDER BY date DESC))[1] AS latest_close
                        FROM (
                            SELECT symbol, volume, close, date,
                                   ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) AS rn
                            FROM price_daily
                            WHERE date >= CURRENT_DATE - INTERVAL '45 days'
                              AND COALESCE(data_unavailable, false) = false
                              AND volume IS NOT NULL AND close IS NOT NULL
                        ) ranked
                        WHERE rn <= 20
                        GROUP BY symbol
                    ) liq_floor ON liq_floor.symbol = ss.symbol"""
