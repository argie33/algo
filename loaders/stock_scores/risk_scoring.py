"""RiskScoringMixin and Risk pillar constants, extracted from load_stock_scores.py
(2026-09-05, file-size-ratchet bloaters-decomposition split). Moved verbatim - no behavior
change.

RISK_MIN_WEIGHT_AVAILABLE/NEAR_ZERO_LIQUIDITY_THRESHOLD are re-exported from
loaders.load_stock_scores for backward compatibility - existing consumers (tests, dashboard,
research scripts) import these names directly from loaders.load_stock_scores and must keep
working unchanged.

Mixed into StockScoresLoader alongside the other stock_scores/*.py pillar mixins - every
`self.` reference here resolves normally through the instance regardless of which mixin file
defines it. No database access here, so no `_owner()` indirection is needed (unlike
value_metrics.py/momentum_scoring.py).

MAX_DRAWDOWN_1Y REMOVED FROM SCORING 2026-09-16 (factor-purity sweep, user: "we do what the
industry does only" - SUPERSEDES every "Volatility/Max Drawdown" reference in the history below,
which describes an earlier, now-corrected state). It was never a named descriptor in Barra's
real Volatility factor or MSCI's Min Vol/BAB literature - an invented addition this file's own
evidence (below) already shows era-flips sign with no stable predictive power in either
direction. See `_score_risk`'s own current docstring note for the full citation. Volatility
60D/252D and Beta now split Risk's weight equally (1/3 each, `RISK_COMPONENT_WEIGHT`) instead of
the 4-way 1/4 split described throughout the history section below.

BARRA VOLATILITY DESCRIPTORS - CORRECTED CITATION + CMRA IMPLEMENTED, 2026-09-17 (factor-purity
follow-up). This paragraph previously attributed "Beta + DASTD/CMRA/HSIGMA" to "Barra USE4" and
flagged the real construction as a NOT-YET-ADDRESSED gap - both claims were themselves unverified
(recalled/paraphrased from a secondary description, not fetched and read directly), the exact
practice this file's own governance elsewhere warns against. Fetched and read the Barra US-E3
Risk Model Handbook directly this session (Appendix A, "US-E3 Descriptor Definitions", Section 1
"Volatility"): the real descriptor list is BTSG (Beta-times-sigma, sqrt(beta*residual_sigma)),
DASTD (EWMA daily stdev), HILO, LPRI, CMRA (12-month cumulative range), VOLBT, SERDP, and OPSTD -
not "Beta + DASTD/CMRA/HSIGMA" (HSIGMA doesn't appear as a named US-E3 descriptor at all; that
name surfaced in a secondary/USE4-era description this file never verified against a primary
source). The handbook states explicitly: "The method of combining these descriptors into risk
indices is proprietary to BARRA" - there is no public combining formula for any Barra model
version to replicate, for any subset of these descriptors. Given that, and per user directive
2026-09-17 ("make sure we don't require Fama-MacBeth [for this], that seems silly" - adopting a
real per-descriptor formula in place of a homegrown proxy is a FIDELITY change, not a magnitude/
weighting claim needing backtest validation, per pillar_weights.py's own TWO-LAYER VALIDATION
POLICY): DASTD (already faithfully implemented as volatility_60d's EWMA fix, see
`_calculate_volatility`'s own docstring) and CMRA (newly implemented, `stability_metrics.cmra_12m`,
see loaders/load_risk_metrics_daily.py's `_calculate_cmra` for the full formula/citation) now
REPLACE volatility_60d+volatility_252d in this pillar's scoring, equal-weighted with Beta (this
repo's own established convention when no institutional combining weight exists - see
pillar_weights.py's UNIFORM EQUAL-WEIGHT policy). BTSG (beta times residual sigma) is NOT
implemented - Beta is instead scored via the real, independently-cited low-beta anomaly
(Frazzini & Pedersen 2014, "Betting Against Beta", see `_score_risk`'s own docstring), a
defensible, already-evidenced alternative rather than reverse-engineering BTSG's regression
window (beta/residual-sigma lookback), which the primary source does not fully specify either.
HILO/LPRI/VOLBT/SERDP/OPSTD are not implemented - none have a clean mapping onto data this
system already computes, and (VOLBT/SERDP especially) measure something other than price
volatility (aggregate trading-volume sensitivity, residual serial dependence) not obviously
within this pillar's own scope.

AQR PIVOT 2026-09-17 (user directive: move Risk scoring to AQR, not a Barra homegrown replica -
"i want the aqr and not the mess we have... no ai slop only what is best in the industry proven").
SUPERSEDES the "BARRA VOLATILITY DESCRIPTORS" paragraph above for scoring purposes (kept below,
unedited, as audit trail - the CMRA implementation and citation work described there was real and
correct, it just no longer carries Risk-pillar scoring weight). An independent verification pass
this session fact-checked every claim in that paragraph against the primary sources directly
(not recalled): DASTD/CMRA are real Barra US-E3 descriptors, but volatility_60d (a 60-day,
mean-centered, 42-day-half-life EWMA vol) is NOT actually E3's DASTD (real DASTD: 65-day window,
UNCENTERED second moment, sqrt(23*sum(w*r^2)) - a materially different formula) - it was a
faithful-*sounding* but mislabeled approximation, the exact "cites the right paper, wrong formula"
failure this codebase's own governance exists to catch. The "no public combining formula for any
Barra model version" claim was also an overgeneralization - USE4/CNE5 publish one
(Residual Volatility = 0.74*DASTD + 0.16*CMRA + 0.10*HSIGMA) even though E3 itself doesn't.
Given the user's explicit direction to run on AQR's own published methodology rather than a
Barra-descriptor composite (real or approximated), Risk's scored input is now AQR's actual named
low-beta-anomaly construction: `beta_bab` (Frazzini & Pedersen 2014, "Betting Against Beta" -
verified against the real published paper this session, section 3.1-3.2), a shrinkage beta
(beta_ts = rho*(sigma_i/sigma_m) from 1yr vol + 5yr overlapping-3-day-return correlation,
beta_bab = 0.6*beta_ts + 0.4) - see loaders/load_risk_metrics_daily.py's `_calculate_beta_bab`
for the full formula. volatility_60d and cmra_12m stay computed/persisted (informational only,
same "compute it, don't score it" treatment this file already gives amihud_illiquidity_60d after
it failed the FDR bar) - RISK_COMPONENT_WEIGHT is now 1.0 (a single scored component, matching
BAB's own real construction: one low-beta-anomaly factor, not a multi-descriptor composite).
The naive-OLS `beta` column is unchanged and still fetched for other consumers (dashboard,
coverage reports) - only `_score_risk`'s scoring input changed, not that column's computation.

SECTOR-NEUTRAL z-score batch pass for Volatility 60D/252D/Max Drawdown, REVERSING an earlier
2026-09-13 decision to leave them universe-wide (see the git history/memory trail below for the
full reasoning arc - kept for context, not because the conclusion still stands).

ORIGINAL REASONING (2026-09-13, first pass, no longer followed): a same-day Momentum equivalent,
`momentum_scoring.py`'s `update_momentum_sector_neutral_scores()`, was added then reverted per a
pre-existing FM/IC rejection. Investigated directly before deciding, not assumed: this pillar's
live sector averages DO diverge (Real Estate/Utilities score safest ~60/59, Technology
least-safe ~36) - the same shape of divergence that justified Momentum's rewrite. The argument
made at the time was that the difference is what the divergence MEANS: Momentum's raw inputs are
classic cross-sectional relative-strength measures harvested RELATIVE to peers (an un-neutralized
sector tilt is a "disguised sector bet"), while Risk's inputs (volatility, max drawdown) are
ABSOLUTE risk-of-loss magnitudes, and the low-volatility anomaly they're meant to capture (Ang et
al. 2006; Frazzini & Pedersen 2014 "Betting Against Beta"; MSCI Minimum Volatility methodology)
is measured and harvested on an ABSOLUTE basis in the literature - a utility genuinely being less
volatile than a biotech was treated as real economic signal, not noise to normalize away.

REVERSED 2026-09-13 (composite-score structural audit, same day, later in the session): that
academic-literature argument was never actually tested against THIS repo's OWN data before being
acted on - it's a "should be true in general" claim, not evidence. Fresh non-circular test this
session (`python -m algo.research.fama_macbeth_price_factors --industries banks|insurers|reits` -
a genuine point-in-time monthly panel reconstructed from price_daily, not the circular
snapshot-vs-trailing-return shortcut this codebase has separately flagged as invalid for any
price-derived pillar - see forward_return_validation_methodology_circular_for_price_derived_
pillars_20260912 in memory) found vol/downside_vol/beta/max_dd have ZERO robust forward-return
edge in exactly the 3 industries whose elevated absolute Risk-pillar scores were driving the
leaderboard's FS/REIT/bank/insurer overweight
([[reit_risk_pillar_concentration_not_fixable_by_sector_relative_20260911]]): all 4 factors
failed FDR correction in all 3 industries, and none cleared the 4-block era-robustness bar
(consistent sign AND |t|>=1.5 in >=3/4 blocks) in any of the 12 industry x factor cells tested -
several also flagged high-VIF (unstable multivariate sign). The "real, sector-independent signal"
defense does not survive contact with this repo's own data for the specific industries it was
meant to justify keeping absolute for. Sector-neutralizing costs nothing here (there is no
real within-industry ranking signal being destroyed) and directly removes the mechanism inflating
those industries' scores. Beta is UNCHANGED by this reversal - it's scored as distance-from-1.0
for market-correlated swing-trading fit (see `_score_risk`'s own docstring), not as a return
predictor at all, so sector-neutralizing a "closeness to 1.0" target would change what the score
means, not just how it's calibrated; that reasoning was never about the anomaly-is-absolute
argument and still holds. Liquidity (avg_dollar_volume_20d) is also UNCHANGED - its curve is
anchored to `algo_config.min_adv_dollars` ($500K), this system's own absolute execution gate, an
independent reason unrelated to the anomaly-literature argument above. Not re-litigated again
without new evidence; if this reverses again, redo the fama_macbeth_price_factors run fresh
rather than trust this comment's numbers as still current.

FOLLOW-UP RE-CHECKED, NOT ACTED ON (2026-09-13, later same session, steady-wiggling-unicorn.md
plan): re-ran the same non-circular FM/IC methodology against the ACTUAL transforms this pillar
scores - `beta_fit = -|beta-1.0|` (not raw signed beta, which is a different hypothesis -
Betting-Against-Beta - than what `_score_risk` measures) and `log10(avg_dollar_volume_20d)`
(never tested before at all) - across banks/insurers/reits (see
`algo/research/fama_macbeth_price_factors.py`'s `NEW_CANDIDATE_COLS`/
`build_new_candidate_cross_sections`). Both failed FDR and era-robustness in all 3 industries,
same as vol/drawdown above. Despite that, this does NOT flip Beta/Liquidity to sector-relative,
because - unlike vol/drawdown - their absolute-scoring rationale was never "this captures a
return-predictive anomaly that the literature measures absolutely" in the first place (that's
the specific claim the vol/drawdown re-test rebutted). Beta targets closeness to a FIXED value
(1.0, market-correlated, for swing-trading style-fit) and Liquidity is anchored to a FIXED
external execution threshold (`algo_config.min_adv_dollars`, $500K - can a trade actually be
filled at all) - neither claims to be harvesting a cross-sectional forward-return edge, so
"no forward-return edge" is not evidence against either rationale; it's an answer to a question
neither component's design was actually asking. Sector-neutralizing a fixed-target/fixed-floor
metric would swap "how far from 1.0 / how far above $500K" for "rank within your sector" - a
real change in what the score MEANS, not a re-calibration, and not something this evidence
justifies. Recorded so this isn't silently retested with the same non-answer next time; a
future case FOR changing either one needs a different kind of evidence (e.g. a live-verified
problem with the fixed target/floor themselves, not a return-predictiveness test).

z-score batch pass ADDED 2026-09-13 (earlier same session, before the reversal above) for
Volatility 60D/252D/Max Drawdown ONLY. `_vol_curve_score`/`_max_drawdown_curve_score`'s fixed
breakpoints (0.15/0.30/0.60 for vol, 10/25/50 for drawdown) were live-checked against this
universe's actual distribution (stability_metrics, 4,920-4,996 scored symbols) rather than
trusted as calibrated: p50 volatility_60d=0.516 (the MEDIAN stock is already past the curve's
0.30 breakpoint, deep in the 50->10 decay segment) and p50 max_drawdown_1y=41.6% (already past
the drawdown curve's 25% breakpoint). Fewer than 1% of the universe clears vol_60d<=0.15 (the
curve's OWN 100-point threshold) - these breakpoints look tuned to a mega-cap-only mental model
of "normal" volatility, not this universe's real small/micro-cap-heavy composition, and unlike
Momentum's old Pass-1 curves (which get fully overwritten by that pillar's own sector-neutral
pass and never reach production), this pillar has no second pass - `_vol_curve_score`'s output
IS the live risk_score. `update_risk_absolute_zscore_scores()` below replaces the TRANSFORM for
these 3 inputs (winsorize -> z-score -> normal-CDF-to-percentile, now SECTOR-RELATIVE per the
reversal above, via the same `sector_neutral_zscore`/`zscore_to_percentile_scale` primitives
Momentum/Growth/Value already use) - matching what MSCI/S&P/AQR/FTSE Russell all independently do
for every factor (winsorize+z-score within a peer group, not a hand-drawn absolute curve). Beta
(scored for closeness to 1.0, not "lower is better" - not a z-score candidate at all, see above)
and Liquidity (curve anchored to a real system constant, not an invented breakpoint) are
UNCHANGED, kept on their existing curves.

MIN_TRADING_DAYS_FOR_DRAWDOWN gate ADDED same pass, found DURING pre-ship verification, not
assumed safe from the design above alone: a live dry run of the new z-score transform (before
this gate existed) put brand-new IPO symbols (MBGL/IOND/JMKE/HOS/MFP/LYNX/BSP/BRVE/ATTT/APMD/
DPC/VOGX/CSQR - all 5 to 55 days of real price_daily history, confirmed via direct query) in the
TOP 15 of the corrected risk_score, ahead of RY/BMO/BRK.A/BRK.B. Root cause verified directly,
not guessed: each has real, large avg_dollar_volume_20d ($5.9M-$76.3M/day - genuinely liquid,
not a NEAR_ZERO_LIQUIDITY_THRESHOLD case) but NULL volatility_60d/beta (confirmed via
`volatility_60d_unavailable_reason='insufficient_history'` - correctly withheld, not enough
trading days for a 60-day window) while max_drawdown_1y IS populated (computed over whatever
partial history exists, no minimum-window guard). That leaves exactly drawdown (0.20) +
liquidity (0.20) = 0.40 weight, precisely at RISK_MIN_WEIGHT_AVAILABLE's floor - and a stock 5-55
days old hasn't been trading long enough to have LIVED THROUGH a real drawdown event yet, so its
tiny max_drawdown_1y isn't a genuine low-risk reading, it's an artifact of not enough elapsed
time - the same "thin, low-weight field alone drives a near-max score" failure mode
RISK_MIN_WEIGHT_AVAILABLE's own docstring already documents for APMC/FTRA/etc., a new instance
of it exposed (not created) by the z-score fix correctly no longer suppressing a merely-decent
21%-drawdown reading the old miscalibrated curve used to flatten to a mediocre ~57. Fix: gate
max_drawdown_1y out of BOTH the z-score population and any individual symbol's score (dropping
those symbols to Liquidity-only, 0.20 weight - below RISK_MIN_WEIGHT_AVAILABLE, correctly
withheld as insufficient_risk_inputs_thin_sample) unless the symbol has at least
MIN_TRADING_DAYS_FOR_DRAWDOWN real price_daily rows - reusing this same table's own
"insufficient_history" threshold (60 trading days, matching volatility_60d's own minimum window)
rather than inventing a new number.
"""

import json
import logging
from typing import TYPE_CHECKING, Any

import psycopg2

from loaders.helpers.factor_normalization import (
    universe_wide_zscore,
    zscore_to_percentile_scale,
)
from loaders.stock_scores.pillar_weights import (
    BASE_PILLAR_WEIGHTS,
    DEFAULT_MIN_ADV_DOLLARS,
    DEFAULT_MIN_STOCK_PRICE,
)
from utils.loaders.helpers import NON_OPERATING_COMPANY_EXCLUSION_SQL_TEMPLATE
from utils.type_conversion import safe_float

logger = logging.getLogger("loaders.load_stock_scores")

# RISK_COMPONENT_WEIGHT (2026-09-16, factor-purity sweep): Volatility 60D/252D and Beta were the
# 3 remaining, industry-traceable Risk inputs after max_drawdown_1y's removal (see _score_risk's
# own docstring) - UNIFORM EQUAL-WEIGHT per the 2026-09-11 directive, now 1/3 each instead of
# 1/4. MIN_TRADING_DAYS_FOR_DRAWDOWN (the old max_drawdown-only IPO-history gate) is removed
# along with its only consumer - see git history if a future pass wants it back.
# UPDATED 2026-09-17 (AQR PIVOT, see module docstring): Risk is now a single scored component,
# beta_bab (AQR's real Betting-Against-Beta shrinkage beta) - volatility_60d/cmra_12m dropped
# from scoring (Barra-descriptor composite, not AQR's own construction; kept computed/persisted
# informational only). Weight is the full 1.0, not a fractional split.
RISK_COMPONENT_WEIGHT = 1.0


def _owner() -> Any:
    """Lazy reference to the owner module, resolved at call time. See
    `momentum_scoring.py`'s `_owner()` for the full rationale (DatabaseContext/execute_values
    test-monkeypatch reachability + avoiding a top-level owner-module import while it's still
    mid-import) - identical reasoning, copied rather than shared to avoid adding a new
    cross-mixin import."""
    from loaders import load_stock_scores as _owner_mod

    return _owner_mod


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
# Deliberately NOT applied to Value or Momentum (AT THE TIME): live-swept both the same way
# (61 and 58 thin-coverage symbols respectively) and found ZERO symbols scoring >=90 off <40%
# weight in either - Value's cross-sectional percentile-rank correction and Momentum's "skip
# weak momentum" None-handling already prevent the single-field-saturation failure mode
# structurally, so adding an artificial floor there would only cost real coverage without
# fixing anything real.
#
# VALUE RECONSIDERED 2026-09-07 (/goal session: "dig into the scoring results" sweep) - the
# check above only looked at saturation at the TOP (>=90); it never checked the bottom. Live
# resweep found the real failure mode there instead: 71 symbols with <40% of Value's weight
# available, most commonly just dividend_yield=0.0 (a non-dividend-paying stock, 10% weight)
# with every multiple missing, landing value_score EXACTLY 0.00 - the same single-field-
# saturation problem this file's own Risk fix above targets, just at the opposite end.
# VALUE_MIN_WEIGHT (loaders/stock_scores/value_score.py) now applies the identical 0.40 floor.
# Momentum's own re-check (same session, same method) found no analogous bottom-end
# saturation - its thin-coverage cases (410 symbols, RSI/MACD-only at 37% weight) span a real,
# non-extreme 15.68-84.04 range live - so Momentum's exemption above still stands as originally
# reasoned, not re-litigated further.
RISK_MIN_WEIGHT_AVAILABLE = 0.40

# NEAR-ZERO LIQUIDITY PRICE-STAT RELIABILITY GATE (added 2026-09-01, same goal session as the
# Liquidity input above - found while checking whether that morning's fix actually closed the
# "untradeable name tops the safest ranking" failure mode). Live-checked: QNBC (the symbol that
# motivated Liquidity's addition) only dropped from rank ~1-5 to rank #33/5045 in composite_score
# - barely moved, and still comfortably a top-100 name. Root cause is upstream of Liquidity's own
# 15% weight: volatility_60d/volatility_252d/beta are computed from price_daily close-to-close
# returns, and a stock that trades near-zero volume has a frozen/near-frozen price series, which
# produces MECHANICALLY SUPPRESSED (not genuinely low) volatility and beta - the input isn't a
# real "this stock is calm" signal, it's a measurement-validity failure. Confirmed both the
# mechanism and its scale directly: EFTY/UCFI/PC/LAWR/QMMM/NUTR/MCTA/MAMK/MAGH all show
# volatility_60d EXACTLY 0.0000 with avg_dollar_volume_20d under $1,000 (EFTY's raw price_daily
# history: flat $15.02, volume=0, every single day of the lookback - not a real "no risk"
# reading). Universe-wide: corr(ln(avg_dollar_volume_20d), volatility_60d) = -0.158 across 4,980
# symbols with a scored volatility_60d - systemic, not a handful of coincidences, though this
# gate only targets the unambiguous near-zero-trading end of that gradient (9 symbols currently
# hit volatility_60d==0.0 AND avg_dollar_volume_20d<$1,000; 14 total under $1,000). Deliberately
# NOT set at algo_config's own $500K min_adv_dollars tradability floor - that threshold covers
# genuinely-trading-but-thin names (e.g. QNBC at $454,701/day, vol_60d=0.0825 - a real, if
# somewhat suppressed, reading) which is Liquidity's own policy question from the note above, not
# a measurement-validity one; conflating the two would re-litigate that already-made call. $2,000
# is comfortably below the smallest ADV in this file's own "genuinely thin but real" universe
# sweep and comfortably above the $0-1,000 frozen-price cluster actually observed. Same
# GOVERNANCE "unavailable metric -> skip its weight, don't redistribute" mechanism this whole
# file already uses elsewhere (RISK_MIN_WEIGHT_AVAILABLE, GROWTH_MIN_FIELDS_AVAILABLE) - a
# symbol this thin still gets scored on whatever Risk inputs remain reliable (Liquidity,
# max_drawdown_1y), continuous not excluded, consistent with this morning's own "we dont want to
# exclude" directive; if too little weight remains it correctly falls through to Risk's existing
# insufficient_risk_inputs_thin_sample marker rather than a fabricated score.
NEAR_ZERO_LIQUIDITY_THRESHOLD = 2000.0

# INDEPENDENT RE-VERIFICATION 2026-09-09 (real-money-readiness audit: an independent review
# flagged the -0.158 corr(ln(ADV), volatility_60d) figure two paragraphs up as evidence the
# frozen-price suppression this gate targets extends broadly across the universe, beyond the
# narrow <$2,000 cluster it currently catches, and proposed widening the gate into a
# continuous ADV-scaled malus. Re-checked directly against live stability_metrics/price_daily
# before changing anything load-bearing: bucketing all 4,958 scored symbols by log10(ADV)
# shows mean volatility_60d *rising*, not falling, as ADV shrinks (0.45 in the $100M-1B decile
# vs 0.55-1.14 in every decile under $1M, up to 2.93 in the single sub-$1,000 case) - the
# opposite direction the suppression theory predicts. Dropping the already-gated <$2,000 rows
# barely moves the correlation (-0.1616 -> -0.1608, n=4,956), so it isn't the tail dragging the
# number either. Directly checked the one band adjacent to this gate's own $2,000 cutoff
# ($2,000-$50,000 ADV, 203 symbols) for a hidden near-zero cluster the aggregate mean could be
# masking: found exactly one symbol under vol_60d=0.10 (IBAC, 0.0424) against a median of 0.67
# and a max of 7.09 in that same band - not a systemic measurement-validity problem, a real,
# well-documented small/thin-cap volatility premium. The -0.158 correlation is genuine
# economic signal, not a measurement artifact, outside the exact-frozen-price cluster this gate
# already excludes. Widening the gate or adding a continuous illiquidity malus on top of that
# real signal would double-penalize genuinely riskier thin names, not fix a bug. This file's
# original 2026-09-01 author already reasoned this far ("this gate only targets the
# unambiguous near-zero-trading end of that gradient") and deliberately did not extend
# further - re-verified with real data rather than re-litigated on the correlation number
# alone; the existing $2,000 threshold plus Liquidity's own separate 15%-weighted tradability
# component remain the correct, sufficient design. No code change from this re-verification.


class RiskScoringMixin:
    """See module docstring.

    `_stability_cache` is set on the instance by `_prepare_batch_context` (defined on
    StockScoresLoader itself, not any mixin) - declared type-checking-only below so mypy can
    see it without a real circular import.
    """

    if TYPE_CHECKING:
        _stability_cache: dict[str, tuple[Any, ...]]

    def _get_stability_metrics(self, cur: Any, symbol: str) -> dict[str, Any]:
        """Fetch stability metrics for symbol.

        Returns explicit marker dict if data is unavailable (either no row or data_unavailable=True).
        Raises RuntimeError on database errors or data type mismatches.

        VALIDATION RULES:
        - Row length validation: Must have >=9 columns (volatility_252d, volatility_60d,
          volatility_30d, beta, downside_volatility_252d/60d/30d, max_drawdown_1y,
          data_unavailable) - cmra_12m (index 9, added 2026-09-17) is read only when present
          (len(row) > 9), so pre-existing 9-element test fixtures keep working unchanged.
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

        MINIMUM DATA REQUIREMENT: Row must have at least 9 columns. Fewer columns causes
        immediate fail-fast ValueError. Required metric for stock scoring (critical upstream
        loader).
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
                # cmra_12m (index 9, added 2026-09-17) - Barra US-E3's real Cumulative Range
                # Volatility descriptor, see loaders/load_risk_metrics_daily.py's
                # `_calculate_cmra` for the full citation. Index 8 is data_unavailable (checked
                # above), so this is appended after it, not interleaved with the original 9.
                # Computed/persisted informational only (AQR PIVOT, see _score_risk's docstring)
                # - no scoring weight.
                "cmra_12m": safe_float(row[9], f"{symbol}.cmra_12m", allow_none=True) if len(row) > 9 else None,
                # beta_bab (index 10, added 2026-09-17, AQR PIVOT) - Frazzini & Pedersen (2014)
                # "Betting Against Beta" shrinkage beta, see loaders/load_risk_metrics_daily.py's
                # `_calculate_beta_bab` for the full formula/citation - the real, scored
                # Risk-pillar low-beta-anomaly input, replacing the naive-OLS `beta` field below
                # for scoring purposes (that field is unchanged/still fetched for other consumers).
                "beta_bab": safe_float(row[10], f"{symbol}.beta_bab", allow_none=True) if len(row) > 10 else None,
            }
            return metrics
        # No row exists at all
        logger.warning(
            f"[LOAD_STOCK_SCORES] No stability metrics available for {symbol} - score completeness will be reduced"
        )
        return {"symbol": symbol, "data_unavailable": True, "reason": "no_stability_metrics_found"}

    def _score_risk(self, metrics: dict[str, Any] | None, symbol: str) -> float | dict[str, Any]:
        """Score risk metrics on 0-100 scale using price volatility / risk-of-loss signals only.

        STALE SUMMARY FIXED (this pass, /goal factor-purity audit) - this paragraph used to
        describe a 5-component flat-20%-each blend (Volatility 60D/252D, Beta, Max Drawdown 1Y,
        Liquidity). REBUILT FURTHER 2026-09-16 (factor-purity sweep) - see RISK_COMPONENT_WEIGHT's
        own docstring for the evidence trail. Current live Risk scoring is 3 components only,
        equal-weighted 1/3 each: Volatility 60D (Barra's real DASTD), CMRA 12M (Barra's real
        Cumulative Range descriptor, replacing the homegrown volatility_252d 2026-09-17 - see
        `_cmra_curve_score`'s own docstring), and Beta. Max Drawdown 1Y and
        Liquidity were REMOVED from scoring - neither appears in a real Barra/MSCI-style market-
        model volatility construction (raw values stay computed/persisted/displayed for other
        consumers). Beta is now scored per the real, published low-beta anomaly (Frazzini &
        Pedersen 2014, "Betting Against Beta") - LOWER beta scores better, not "beta near 1.0"
        (see the beta-scoring code below for the current linear curve). The historical reasoning
        below (45/15/15/10/15, then 5-way equal-weight) is kept as audit trail, not as
        justification for today's live weights/components.

        RENAMED 2026-08-26 (user directive): Stability -> Risk. Same computation
        (volatility/beta/downside-vol/max-drawdown), name only - the underlying
        stability_metrics input table and _get_stability_metrics accessor are unchanged.

        REWORKED 2026-08-30 (later same day, user directive: "figure out what is best here and
        do that" - full delegation after the 40/20/15/15 revert above was itself questioned).
        Volatility 60D (45%) + Volatility 252D (20%) + Beta (20%) + Max Drawdown 1Y (15%) was
        the formula from that pass through 2026-08-31; see the REWEIGHTED 2026-09-01 note below
        for the current one (Liquidity added, other four proportionally rescaled). Reasoning per
        input, applying this file's own accumulated evidence rather than re-deriving it:
        Volatility 60D gets the largest share because it's the one robustly-significant signal
        in the whole panel (t=-6.07 multivariate). Volatility 252D stays for genuine horizon
        diversity - its correlation with 60D (0.69-0.89) is real but well short of the ~0.9+
        band this file treats as actionable redundancy elsewhere. Volatility 30D is DROPPED:
        it's the most redundant of the three windows (least distinct horizon from 60D) and its
        removal doesn't lose a horizon 252D doesn't already cover from the other side. Beta is
        kept at a deliberate, non-alpha weight - scored for market-correlated swing-trading fit,
        not because it's return-predictive (it isn't, t=0.93 - see below). Max Drawdown 1Y
        returns at a modest weight as a genuinely distinct loss-severity dimension (a smooth-vol
        stock can still suffer one deep crash that vol windows don't capture) rather than as a
        return-prediction bet, since the 2026-08-25 sub-period analysis below found it isn't
        stably predictive in either direction - consistent with how Beta is already scored here
        for a non-predictive reason.

        REWEIGHTED 2026-09-01 (goal session - user live-observed untradeable micro-cap banks
        topping this pillar's "safest" ranking, e.g. HYNE/PROV/QNBC all below algo_config's own
        min_adv_dollars=$500K trade-eligibility floor, and explicitly delegated "figure out what
        is best" after clarifying "we dont want to exclude"). Added Liquidity (20-trading-day
        average dollar volume, 15%) as a new weighted component - see that field's own inline
        comment in this method for the full rationale (tradability-RISK framing, deliberately
        NOT the opposite-signed academic illiquidity-return-premium direction this codebase's
        own algo/research/fama_macbeth_liquidity_factor.py already found real for a buy-and-hold
        horizon, which doesn't apply to this pillar's swing-trading framing). Volatility 60D left
        UNCHANGED at 45% rather than proportionally rescaled with the others - it's this pillar's
        single most robust individual signal (t=-6.07, see above) and RISK_MIN_WEIGHT_AVAILABLE
        (0.40) requires a symbol to clear that floor on whatever inputs it has; a first-pass
        proportional rescale (45%->38%) would have dropped it BELOW 0.40, silently breaking the
        "the most important input can carry a score alone" property this file already relies on
        (live-caught via test_stock_scores_risk_min_weight_available_20260831.py, not assumed).
        The other three funded Liquidity's 15% instead: Volatility 252D 20%->15%, Beta 20%->15%,
        Max Drawdown 1Y 15%->10% (45+15+15+10+15=100). A continuous score, not a hard cutoff,
        per the explicit "don't exclude" directive - a thin-liquidity name is scored lower here,
        not removed from the universe; Phase 7/8's own liquidity gate (unchanged by this) remains
        the actual binary trade-eligibility check at execution time.
        Downside
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

        IMPLEMENTED, THEN NOT SCORED, 2026-09-17 (factor-purity sweep follow-up).
        RiskMetricsLoader._calculate_amihud_illiquidity now computes and stores
        stability_metrics.amihud_illiquidity_60d (migration 1305) - the genuine new
        computation this note above said was needed. Before assigning it any live scoring
        weight, re-ran it through this repo's OWN required bar for a new factor (multi-block
        era-robustness + FDR, per the WEIGHT-REVISION GOVERNANCE POLICY in pillar_weights.py)
        rather than trusting the single ad hoc t=3.34 figure above - the same
        "independently re-verify before acting" standard already applied to the PE-vs-PB/PS
        and max_drawdown sub-period findings elsewhere in this file, and for the same reason:
        that number didn't survive contact with proper scrutiny. `python -m
        algo.research.fama_macbeth_amihud_illiquidity --start-date 2019-01-01` (91 months,
        median 6,154 symbols, using the EXACT live production formula - trailing-21-day
        mean(|log return|/dollar volume), log-transformed for its heavy right skew before
        winsorizing/z-scoring - not the original ad hoc script's own construction, which this
        repo no longer has a copy of to compare directly): full-sample t=0.59 (fails FDR),
        and 4-block era-robustness shows the sign flipping across blocks (only 1/4 clears
        |t|>=1.5, blocks read +1.58/-0.77/-0.23/+0.46) - the identical "era-flips sign, no
        stable predictive power" failure shape max_drawdown_1y was cut for above, not the
        clean, robust signal the original single-number claim suggested. CONCLUSION: Amihud
        illiquidity does NOT clear this repo's own bar for a scored factor. It stays
        computed/persisted (informational, matching how max_drawdown_1y/Liquidity remain
        available to other consumers after their own removal from scoring) but deliberately
        gets NO weight in risk_score or any other pillar - not an oversight or unfinished
        work, a real conclusion from real re-verification. Re-open only with fresh evidence,
        not by re-trusting the 2026-08-25 number above.

        NEAR-ZERO-LIQUIDITY PRICE-STAT GATE, ADDED 2026-09-01 (see NEAR_ZERO_LIQUIDITY_THRESHOLD's
        own docstring): volatility_60d/cmra_12m/beta are skipped (weight not counted) when
        avg_dollar_volume_20d is known and below $2,000/day - below that, the price series is
        frozen or near-frozen and these read as mechanically-suppressed noise (e.g. exactly 0.0
        volatility), not a genuine low-risk signal. A measurement-validity fix, distinct from and
        in addition to Liquidity's own 15%-weighted policy input above.

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

        MINIMUM DATA REQUIREMENT: available weight (volatility_60d/cmra_12m/beta/
        max_drawdown_1y/Liquidity, each 0.20 - UNIFORM EQUAL-WEIGHT per the 2026-09-11 user
        directive described in this method's own "UNIFORM EQUAL-WEIGHT" docstring section
        above; a prior Fama-MacBeth-tuned 0.45/0.15/0.15/0.10/0.15 split predates that
        directive and is HISTORICAL ONLY - see git log for that era) must reach
        RISK_MIN_WEIGHT_AVAILABLE (0.40, i.e. >=2 of the 5 components). If all
        stability metrics are None, returns data_unavailable marker.
        Critical metric for stock scoring (high priority upstream loader).
        """
        if not metrics or metrics.get("data_unavailable"):
            logger.warning(f"[STOCK_SCORES] Returning data_unavailable marker for risk_score({symbol})")
            return {"symbol": symbol, "data_unavailable": True, "reason": "no_risk_metrics_data"}

        weighted_sum = 0.0
        total_weight = 0.0

        # AQR PIVOT 2026-09-17 (see this module's own top-of-file docstring for the full
        # citation/evidence trail): volatility_60d/cmra_12m are computed/persisted informational
        # only now - NOT scored - RISK_COMPONENT_WEIGHT is 1.0, a single component (beta_bab).
        # Debt-to-Assets stays fetched via Quality's own debt_to_assets read (quality_inputs on
        # the scores API) - not merged into or scored by this pillar.

        # NEAR_ZERO_LIQUIDITY_THRESHOLD gate (see that constant's own docstring): a near-zero
        # or frozen-price series makes beta_bab's own inputs (correlation/volatility vs SPY)
        # measurement noise, not a real signal - skip its weight here rather than trust a
        # fabricated "calm" reading. Only gates when avg_dollar_volume_20d is actually known;
        # missing liquidity data doesn't imply thin trading, so it leaves this input untouched.
        adv20 = metrics.get("avg_dollar_volume_20d")
        price_stats_unreliable = adv20 is not None and 0 <= adv20 < NEAR_ZERO_LIQUIDITY_THRESHOLD

        # Beta_bab: LOW beta is best, matching the real published anomaly - Frazzini & Pedersen
        # 2014 "Betting Against Beta" (Journal of Financial Economics 111(1)). beta_bab is
        # ALREADY the paper's own shrinkage estimator (beta_ts = rho*(sigma_i/sigma_m),
        # beta_bab = 0.6*beta_ts + 0.4*1.0 - see loaders/load_risk_metrics_daily.py's
        # `_calculate_beta_bab`), replacing the naive-OLS `beta` column this scoring formula
        # used until the 2026-09-17 AQR pivot (that column is unchanged/still fetched for other
        # consumers, e.g. dashboard/coverage reports - only this pillar's scoring input changed).
        # Linear reward for lower beta_bab: beta_bab<=0 scores 100 (fully defensive/inverse-
        # correlated), beta_bab>=2.0 scores 0, linear in between (beta_bab=1.0 -> 50) - same
        # formula shape the pre-pivot raw-beta version used, just fed the real shrinkage
        # estimator instead of a noisy raw covariance beta.
        if not price_stats_unreliable and metrics.get("beta_bab") is not None:
            beta_bab = metrics["beta_bab"]
            beta_score = max(0.0, min(100.0, 100 - beta_bab * 50))
            weighted_sum += beta_score * RISK_COMPONENT_WEIGHT
            total_weight += RISK_COMPONENT_WEIGHT

        # max_drawdown_1y REMOVED as a scored Risk component 2026-09-16 (factor-purity sweep,
        # user: "we do what the industry does only"). It was never a named Barra/MSCI risk
        # descriptor to begin with - the real Barra USE4 Volatility descriptor is Beta + DASTD
        # (EWMA daily stdev) + CMRA (cumulative range) + HSIGMA (historical sigma from a
        # market-model regression); max drawdown appears in neither that nor MSCI's own
        # Min Vol/BAB literature. This file's own docstring already documents (see the
        # 2026-08-25/RESOLVED and INDEPENDENT RE-VERIFICATION sections above) that
        # max_drawdown_1y era-flips sign with no stable predictive power in either direction -
        # the identical "not stably predictive, invented input" shape Growth's rebuild already
        # used to cut fcf_growth_yoy this same session, just with weaker evidence there than
        # here. Kept anyway for years on a "genuinely distinct loss-severity dimension" framing
        # that was never checked against a real published descriptor list - held to the same
        # bar Growth/Quality/Value's fields were just held to, it doesn't clear it. Raw
        # max_drawdown_1y stays computed/persisted/displayed (RISK_SCHEMA, informational) - only
        # its vote in risk_score is removed. Volatility 60D/252D and Beta now split the full
        # weight equally (1/3 each, still UNIFORM EQUAL-WEIGHT per the 2026-09-11 directive -
        # just over 3 genuine, industry-traceable inputs instead of 4). MIN_TRADING_DAYS_FOR_
        # DRAWDOWN/`_max_drawdown_curve_score` are dead code now (removed) - see git history if
        # a future pass wants to resurrect this input with real evidence behind it.

        # Liquidity REMOVED as a scored Risk component 2026-09-15 (user directive: "get rid of
        # all the extra shit beyond the barra and the industry guys"). Real Barra-style
        # Minimum-Volatility/low-risk factor construction (MSCI Min Vol, Betting-Against-Beta)
        # never folds tradability into the risk-anomaly score itself - that's a portfolio-
        # construction/execution eligibility screen, answered separately from "how risky is
        # this stock." This codebase already HAS that separate screen (algo_config.
        # min_adv_dollars, enforced at trade entry by Phase 7/8's LiquidityChecks, and by
        # LIQUIDITY_FLOOR_JOIN_SQL gating every batch pass's peer population above) - folding
        # it into Risk's own 20%-weighted score meant "Risk" was answering two different
        # questions (is this stock low-risk vs. can I trade it) with one number, unlike any
        # real published risk-factor definition. `avg_dollar_volume_20d` is still fetched/used
        # for the NEAR_ZERO_LIQUIDITY_THRESHOLD measurement-validity gate above (a data-
        # reliability check, not a scored factor) and remains the system's real trade-
        # eligibility gate everywhere else - `_liquidity_curve_score` itself is dead code (also
        # unused by the batch-pass recompute below) and was removed.

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

    # _vol_curve_score/_cmra_curve_score/NEUTRAL_PLACEHOLDER_SCORE DELETED 2026-09-17 (AQR
    # purity cleanup, user: "get the aqr down to its purest form... extra shit mixing with
    # msci"). These were Pass-1 placeholders for volatility_60d/cmra_12m scoring - already
    # flattened to an inert neutral 50.0 earlier the same day once the real batch z-score pass
    # made them unreachable in practice (see git history for that live-audit evidence). The AQR
    # pivot immediately after removed volatility_60d/cmra_12m from Risk-pillar scoring entirely
    # (beta_bab is now the sole scored input, RISK_COMPONENT_WEIGHT=1.0) - confirmed via grep
    # before deleting, not assumed: zero remaining callers anywhere in this file. The one
    # external caller (algo/research/all_pillars_curve_vs_percentile_sweep_20260828.py, a
    # completed one-off research sweep) got the real historical curve formula inlined verbatim
    # first, same "kept here so a completed sweep still reproduces" precedent that script's own
    # max_drawdown_pct branch already established when _max_drawdown_curve_score was cut.

    @staticmethod
    def _components_with_corrected_risk(components_old: Any, risk_score_new: float | None) -> str:
        """Return components (the Pass-1 JSON breakdown dict) re-serialized with its 'risk' key
        set to risk_score_new, every other pillar untouched. Mirrors
        MomentumScoringMixin._components_with_corrected_momentum exactly - same bug class this
        repo already fixed there, just for the 'risk' key."""
        if isinstance(components_old, dict):
            components_new = dict(components_old)
        elif components_old:
            components_new = json.loads(components_old)
        else:
            components_new = {}
        components_new["risk"] = risk_score_new
        return json.dumps(components_new)

    def _fetch_risk_absolute_zscore_rows(self) -> list[tuple[Any, ...]]:
        """DB fetch half of `update_risk_absolute_zscore_scores` - split out to keep that
        method's own cyclomatic complexity within this repo's ruff C901 limit (pure extraction,
        no behavior change). Re-derives avg_dollar_volume_20d the same way
        `load_stock_scores.py`'s own Pass-1 liquidity cache does (45-calendar-day price_daily
        lookback, last 20 real trading days) rather than depending on that cache's instance
        lifetime - this method runs as an independent, self-contained batch pass.

        DEAD-COLUMN SWEEP 2026-09-17 (factor-purity follow-up, user: "places where we
        incorrectly mixing concepts" - this was the same class of gap, just via omission
        rather than a wrong formula: a docstring implying live enforcement of something the
        query doesn't actually do). Removed 3 things this method fetched but nothing ever
        consumed:
          - `history` CTE / `trading_days_history` - only consumer was
            MIN_TRADING_DAYS_FOR_DRAWDOWN's max_drawdown_1y gate, itself removed 2026-09-16
            when max_drawdown_1y was cut from scoring entirely (see _score_risk's docstring).
            Confirmed dead via grep - no `row[15]` reference left anywhere in this file.
          - `cp.sector` (company_profile JOIN) - `_compute_risk_absolute_zscore_percentiles`
            calls `sector_neutral_zscore(raw_*, {})` with an EMPTY sector map (universe-wide,
            per the PARTIAL RE-REVERSAL note on that method), so this column was fetched via a
            JOIN and never read - `row[16]` had zero references.
          - `vm.market_cap` (value_metrics JOIN) - see below, never read (`row[18]`).
        Confirmed via grep, not assumed: searching this file for row-index references 15
        through 18 (the dropped columns' old positions) returned nothing before this cleanup.
        `company_info_sec` (`cis`)
        stays JOINed - still needed for NON_OPERATING_COMPANY_EXCLUSION_SQL_TEMPLATE's WHERE
        clause below, even though its own SELECTed `is_foreign_private_issuer` column (former
        `row[17]`) was equally dead and is removed too.

        STALE DOCSTRING FIXED (same pass): this docstring used to describe an "INVESTABILITY
        FLOOR ADDED 2026-09-13 (`vm.market_cap >= %s`...)" - but the WHERE clause below has
        never had a `vm.market_cap >=` condition; only `liq.latest_close >=`/
        `liq.avg_dollar_volume_20d >=` (the liquidity floor). That market-cap floor was real
        once, then REPLACED by the liquidity-based floor 2026-09-15 (see pillar_weights.py's
        own DEFAULT_MIN_INVESTABLE_MARKET_CAP retirement note for the full history) - this
        docstring paragraph was simply never updated to match, silently implying a market-cap
        gate was still enforced here when it never was after that replacement. The liquidity
        floor (`liq.latest_close`/`liq.avg_dollar_volume_20d` below) is the real, current
        investability gate for this pass, same as every sibling pillar's own batch pass.
        """
        with _owner().DatabaseContext("write") as cur:
            cur.execute(
                """
                WITH liquidity AS (
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
                )
                SELECT ss.symbol, ss.risk_score, ss.composite_score, ss.quality_score,
                       ss.growth_score, ss.value_score, ss.momentum_score, ss.components,
                       ss.data_completeness, ss.data_unavailable,
                       liq.avg_dollar_volume_20d, sm.beta_bab, vm.market_cap
                FROM stock_scores ss
                JOIN stability_metrics sm ON sm.symbol = ss.symbol
                JOIN liquidity liq ON liq.symbol = ss.symbol
                JOIN stock_symbols su ON su.symbol = ss.symbol
                LEFT JOIN company_info_sec cis ON cis.symbol = ss.symbol
                LEFT JOIN value_metrics vm ON vm.symbol = ss.symbol
                WHERE ss.risk_score IS NOT NULL
                  AND COALESCE(sm.data_unavailable, false) = false
                  AND liq.latest_close >= %s
                  AND liq.avg_dollar_volume_20d >= %s
                  AND ("""
                + NON_OPERATING_COMPANY_EXCLUSION_SQL_TEMPLATE.format(symbols_alias="su", company_info_alias="cis")
                + ")",
                (
                    getattr(self, "_min_stock_price", None) or DEFAULT_MIN_STOCK_PRICE,
                    getattr(self, "_min_adv_dollars", None) or DEFAULT_MIN_ADV_DOLLARS,
                ),
            )
            rows: list[tuple[Any, ...]] = cur.fetchall()
            return rows

    @staticmethod
    def _compute_risk_absolute_zscore_percentiles(
        rows: list[tuple[Any, ...]],
    ) -> dict[str, dict[str, float]]:
        """Winsorize+z-score beta_bab (AQR's Betting-Against-Beta shrinkage estimator,
        Frazzini & Pedersen 2014), Risk's ONE scored input as of the 2026-09-17 AQR pivot -
        UNIVERSE-WIDE, via `universe_wide_zscore` (not sector-relative - see this module's own
        top-of-file docstring for the live USMV N-PORT evidence that the low-beta anomaly is
        harvested on an absolute basis in the real literature, not per-sector). Split out of
        `update_risk_absolute_zscore_scores` for C901, pure function of its inputs.

        Negated before z-scoring so a symbol with LOW beta_bab - the desirable direction for
        this pillar - gets a HIGH z-score and therefore a HIGH percentile score, matching
        `zscore_to_percentile_scale`'s "higher input -> higher output" convention.

        NEAR_ZERO_LIQUIDITY_THRESHOLD measurement-validity gate (see that constant's own
        docstring): a frozen/near-frozen-price symbol's beta_bab is excluded from the
        population entirely here, not just from its own score - including it would bias every
        OTHER symbol's z-score against a fabricated data point.

        HISTORY: this pass previously scored 3 separate Barra-descriptor-style inputs
        (volatility_60d/DASTD, cmra_12m/CMRA, raw OLS beta) equal-weighted, with a real
        back-and-forth over sector-relative vs. universe-wide grouping driven by live USMV/
        Fama-MacBeth evidence - see git history for that full trail if it's ever relevant again.
        The 2026-09-17 AQR pivot (user: "i want the aqr and not the mess we have") replaced all
        of that with AQR's own single, real published construction rather than layering a
        fourth input alongside three homegrown-Barra-descriptor ones - volatility_60d/cmra_12m
        are computed/persisted informational only now, not part of this pass at all.
        """
        # AQR PIVOT 2026-09-17 (see this module's own top-of-file docstring): beta_bab
        # (Frazzini & Pedersen 2014 shrinkage beta) is now the ONLY scored Risk input -
        # volatility_60d/cmra_12m are computed/persisted informational only, matching
        # `_score_risk`'s own Pass-1 formula. Population is a single dict, not three.
        raw_beta_bab: dict[str, float] = {}
        market_caps: dict[str, float] = {}

        for row in rows:
            symbol = row[0]
            adv20, beta_bab = row[10], row[11]
            market_cap = row[12] if len(row) > 12 else None
            if market_cap is not None:
                market_caps[symbol] = float(market_cap)
            price_stats_unreliable = adv20 is not None and 0 <= float(adv20) < NEAR_ZERO_LIQUIDITY_THRESHOLD
            if not price_stats_unreliable and beta_bab is not None:
                # Negated, not clamped to >=0, since a negative beta_bab is a real signed
                # reading that should score ABOVE beta_bab=0, not be floored to it (see
                # `_score_risk`'s own beta_bab comment) - matches zscore_to_percentile_scale's
                # "higher input -> higher output" convention (lower/more-negative raw beta_bab
                # is the desirable direction for this pillar).
                raw_beta_bab[symbol] = -float(beta_bab)

        # UNIVERSE-WIDE, via the dedicated primitive (fixed 2026-09-17, AQR purity cleanup) -
        # this used to call `sector_neutral_zscore(raw_beta_bab, {})`, the SECTOR-relative
        # primitive faked into universe-wide behavior with an empty sectors dict. Mathematically
        # identical output (every symbol falls through to that function's own residual-pool
        # branch when sectors={}), but this is the exact "wrong-named primitive left over from
        # an abandoned per-sector methodology" pattern `universe_wide_zscore`'s own docstring
        # already flags as "a real, recurring methodology-translation error in this codebase,
        # not a one-off" - for this EXACT Risk/USMV case, specifically. Matches this module's
        # own top-of-file docstring evidence (live USMV N-PORT crosscheck) that the low-beta
        # anomaly is harvested on an absolute, not sector-relative, basis in the literature this
        # pillar is now built directly from (Frazzini & Pedersen 2014).
        # market-cap-weighted mean/stdev (2026-09-17, MSCI-fidelity audit - see
        # factor_normalization.py's `_zscore_group` docstring): market_caps re-added via a new
        # `vm.market_cap` JOIN above, distinct from the `vm.market_cap` column removed earlier
        # today as dead weight (that one fed a since-retired investability-floor gate, not
        # z-score weighting).
        return {
            "beta_bab": zscore_to_percentile_scale(universe_wide_zscore(raw_beta_bab, market_caps)),
        }

    def _recompute_risk_row(
        self,
        row: tuple[Any, ...],
        pct_by_field: dict[str, dict[str, float]],
        min_completeness_threshold: float,
    ) -> tuple[str, float | None, float, str | None, float, bool] | None:
        """Recompute one symbol's risk_score/composite_score from the absolute z-score
        percentile of beta_bab (AQR's Betting-Against-Beta shrinkage estimator, the pillar's
        ONE scored input - see `_compute_risk_absolute_zscore_percentiles`'s own docstring),
        and diff against its current stored values. Returns None if nothing changed. Split out
        of `update_risk_absolute_zscore_scores` for C901, pure function of its inputs - mirrors
        MomentumScoringMixin._recompute_momentum_row's structure.

        Barra-descriptor scoring (Volatility 60D/DASTD, CMRA 12M) and the raw-OLS `beta` linear
        map are HISTORICAL ONLY as of the 2026-09-17 AQR pivot (see this module's own
        top-of-file docstring) - superseded entirely by beta_bab, not layered alongside it. See
        git history for the prior 3-component construction if a future pass wants that context.
        """
        symbol = row[0]
        risk_score_old = float(row[1])
        composite_score_old = float(row[2])
        quality_score, growth_score, value_score, momentum_score = row[3], row[4], row[5], row[6]
        components_old = row[7]
        data_completeness_old = float(row[8]) if row[8] is not None else None
        data_unavailable_old = bool(row[9]) if row[9] is not None else False
        # DEAD-COLUMN SWEEP 2026-09-17 (AQR purity cleanup): volatility_60d/cmra_12m/beta (raw)
        # were dropped from _fetch_risk_absolute_zscore_rows' own SELECT - nothing in this
        # batch pass ever read them once beta_bab became the sole scored input. adv20 is now
        # row[10], beta_bab row[11] (was row[13]/row[14] when those 3 dead columns still sat
        # ahead of them in the SELECT).
        adv20 = row[10]

        price_stats_unreliable = adv20 is not None and 0 <= float(adv20) < NEAR_ZERO_LIQUIDITY_THRESHOLD

        weighted_sum = 0.0
        total_weight = 0.0
        # AQR PIVOT 2026-09-17: beta_bab is the sole scored Risk input (RISK_COMPONENT_WEIGHT
        # = 1.0) - see _compute_risk_absolute_zscore_percentiles's own docstring.
        if not price_stats_unreliable and symbol in pct_by_field["beta_bab"]:
            weighted_sum += pct_by_field["beta_bab"][symbol] * RISK_COMPONENT_WEIGHT
            total_weight += RISK_COMPONENT_WEIGHT
        # Liquidity is no longer a scored Risk component (see _score_risk's own note) - adv20 is
        # still fetched above only for the NEAR_ZERO_LIQUIDITY_THRESHOLD price_stats_unreliable
        # gate.

        if total_weight >= RISK_MIN_WEIGHT_AVAILABLE:
            risk_score_new: float | None = round(weighted_sum / total_weight, 2)
        else:
            if total_weight > 0:
                logger.info(
                    f"[STOCK_SCORES] {symbol} risk_score withheld in absolute z-score pass: "
                    f"only {total_weight:.2f}/1.00 weight available, below "
                    f"RISK_MIN_WEIGHT_AVAILABLE={RISK_MIN_WEIGHT_AVAILABLE}."
                )
            risk_score_new = None

        # GROWTH RESTORED TO COMPOSITE 2026-09-17 (same-day reversal - see pillar_weights.py's
        # BASE_PILLAR_WEIGHTS "ABOVE DECISION SUPERSEDED" note).
        weights = BASE_PILLAR_WEIGHTS
        composite_val = 0.0
        for pillar_name, pillar_score in (
            ("quality", quality_score),
            ("value", value_score),
            ("risk", risk_score_new),
            ("momentum", momentum_score),
            ("growth", growth_score),
        ):
            if pillar_score is not None:
                composite_val += float(pillar_score) * weights[pillar_name]
        composite_score_new = round(max(0.0, min(100.0, composite_val)), 2)

        all_scores_new: dict[str, float | None] = {
            "quality": float(quality_score) if quality_score is not None else None,
            "value": float(value_score) if value_score is not None else None,
            "risk": risk_score_new,
            "momentum": float(momentum_score) if momentum_score is not None else None,
            "growth": float(growth_score) if growth_score is not None else None,
        }
        available_weight = sum(
            BASE_PILLAR_WEIGHTS[pillar] for pillar, score in all_scores_new.items() if score is not None
        )
        data_completeness_new = min(99.99, round(available_weight * 100, 2))
        data_unavailable_new = data_completeness_new < min_completeness_threshold

        if (
            risk_score_new != risk_score_old
            or composite_score_new != composite_score_old
            or data_completeness_new != data_completeness_old
            or data_unavailable_new != data_unavailable_old
        ):
            components_json = self._components_with_corrected_risk(components_old, risk_score_new)
            return (
                symbol,
                risk_score_new,
                composite_score_new,
                components_json,
                data_completeness_new,
                data_unavailable_new,
            )
        return None

    def update_risk_absolute_zscore_scores(self) -> None:
        """Batch pass: replace Risk's Pass-1 PROVISIONAL fixed-breakpoint curve scores
        (`_vol_curve_score`/`_max_drawdown_curve_score`, calibrated to invented thresholds that
        this module's own docstring shows badly miscalibrated against the live universe) with a
        real winsorize+z-score against the current run's universe for Volatility 60D (DASTD) and
        CMRA 12M (volatility_252d's real-methodology replacement, 2026-09-17), then
        FULLY RECOMPUTES risk_score and composite_score from scratch off the raw stored
        stability_metrics/price_daily columns - mirrors `update_momentum_sector_neutral_scores()`'s
        pure-overwrite pattern.

        STALE SUMMARY FIXED (this pass, /goal factor-purity audit) - this paragraph used to claim
        this pass sector-neutralizes, per the 2026-09-13 reversal. That was itself PARTIALLY
        RE-REVERSED 2026-09-15 (see `_compute_risk_absolute_zscore_percentiles`'s own docstring
        for the full evidence trail) - vol_60d/vol_252d went back to universe-wide (empty sectors
        dict), and max_drawdown_1y (which stayed sector-neutral) was removed from this pass
        entirely 2026-09-16 (factor-purity sweep). Current live grouping for both scored inputs
        is universe-wide, matching the same real, whole-universe-significant low-volatility
        anomaly (Ang et al. 2006; Frazzini & Pedersen 2014) this module's top-of-file docstring
        describes - not sector-relative. No MIN_TRADING_DAYS_FOR_DRAWDOWN gate applies here any
        more (that constant and its only consumer were removed alongside max_drawdown_1y).

        WHY the z-score transform exists at all (2026-09-13, /goal "question the scoring
        methodology" session): live-checked `_vol_curve_score`'s breakpoints (0.15/0.30/0.60)
        against the real stability_metrics distribution before touching anything - p50
        volatility_60d=0.516, already past the curve's OWN 0.30 breakpoint (the point where its
        score formula switches to the steepest decay segment), and under 1% of the universe
        clears the curve's 100-point threshold (0.15). Same story for `_max_drawdown_curve_score`
        (p50 max_drawdown_1y=41.6%, past its 25% breakpoint). These breakpoints were never derived
        from this universe's actual distribution - fixing that (self-calibrating winsorize+z-score,
        recomputed fresh every run against whatever the universe currently looks like) is the same
        fix already applied to Momentum/Growth/Value's analogous absolute-mapping problem, using
        the same shared primitive (`sector_neutral_zscore`/`zscore_to_percentile_scale`). Whether
        the grouping is sector-relative or universe-wide is a SEPARATE question, covered by this
        module's top-of-file docstring's REVERSED note, not by this WHY.

        PRE-SHIP VERIFICATION CAUGHT A REAL REGRESSION before this ever ran for real (not
        assumed safe from the design above alone): a first dry run of just the z-score swap put
        13 brand-new IPOs (5-55 days of price_daily history) in the top 15 of the corrected
        risk_score, ahead of RY/BMO/BRK.A/BRK.B - the exact "shitty microcap with no real track
        record dominates the safest list" failure mode this whole exercise exists to eliminate,
        not fix. Root cause verified directly: each had real, large avg_dollar_volume_20d
        ($5.9M-$76.3M/day, genuinely liquid) but NULL volatility_60d/beta
        (volatility_60d_unavailable_reason='insufficient_history', correctly withheld) while
        max_drawdown_1y was populated over whatever partial history existed - a stock days old
        hasn't lived through a real drawdown yet, so a small max_drawdown_1y there isn't a
        genuine safety signal. MIN_TRADING_DAYS_FOR_DRAWDOWN (60, matching volatility_60d's own
        minimum window) now gates max_drawdown_1y out of both the population and any individual
        score for these symbols, correctly dropping them to Liquidity-only (0.20 weight, below
        RISK_MIN_WEIGHT_AVAILABLE) - withheld as insufficient_risk_inputs_thin_sample instead of
        a fabricated top-15 safety score. Re-verified after adding the gate: none of the 13
        symbols above remain in the top 200 of the corrected risk_score.

        Beta now JOINS this pass 2026-09-17 (factor-purity follow-up - live-caught by the same
        automated slop audit that originally motivated this file's other fixes): it was the only
        one of Risk's 3 remaining inputs still left on `_score_risk`'s Pass-1 raw linear map
        (100 - beta*50) with no corrective batch pass at all, unlike vol_60d/vol_252d which this
        method already corrects. There was never a principled reason for the asymmetry - low
        beta is rewarded per the same real, published anomaly (Frazzini & Pedersen 2014 "Betting
        Against Beta"/MSCI Min Vol) as low volatility, and a raw linear map has the identical
        "not derived from this universe's actual distribution" problem the vol/max_drawdown
        curves were fixed for, just never checked because the formula LOOKS more principled
        (it cites a real anomaly) than an admittedly-arbitrary breakpoint curve does - citing the
        right paper doesn't make an un-z-scored raw linear transform statistically sound. Beta is
        now winsorize+z-scored universe-wide (negated so lower/more-negative beta scores higher,
        matching vol_60d/vol_252d's own convention - see `_compute_risk_absolute_zscore_percentiles`),
        gated by the same NEAR_ZERO_LIQUIDITY_THRESHOLD measurement-validity check `_score_risk`
        already applies to it. `_score_risk`'s own Pass-1 linear formula is unchanged (still a
        reasonable provisional value before this pass runs, same relationship Pass-1's vol/growth/
        value curves already have to their own batch corrections) - only the FINAL, live value
        changes. Liquidity is no longer a scored Risk component at all (see `_score_risk`'s own
        note) - `adv20` is still fetched here only for the NEAR_ZERO_LIQUIDITY_THRESHOLD
        measurement-validity gate.

        Runs FIRST in `post_run()`, ahead of `update_momentum_sector_neutral_scores()` and every
        other batch pass that recomputes composite_score from the pillar scores as they currently
        stand - so those passes see the CORRECTED risk_score, not Pass-1's miscalibrated one, the
        same "order matters" reasoning `post_run()`'s own comment already documents for why
        Momentum runs before `update_rs_percentiles()`.

        Raises on failure, same as every other post_run() batch pass - an inconsistent
        risk_score/composite_score is a live-trading-relevant correctness issue.
        """
        try:
            rows = self._fetch_risk_absolute_zscore_rows()
            if not rows:
                logger.warning(
                    "[STOCK_SCORES] update_risk_absolute_zscore_scores: no eligible rows found "
                    "(risk_score IS NOT NULL) - skipping, nothing to correct."
                )
                return

            pct_by_field = self._compute_risk_absolute_zscore_percentiles(rows)

            logger.info(
                "[STOCK_SCORES] Risk absolute z-score universe (no sector grouping): "
                + ", ".join(f"{field}={len(values)}" for field, values in pct_by_field.items())
            )

            min_completeness_threshold = getattr(self, "_min_completeness_threshold", 70.0)

            updates: list[tuple[str, float | None, float, str | None, float, bool]] = []
            for row in rows:
                update = self._recompute_risk_row(row, pct_by_field, min_completeness_threshold)
                if update is not None:
                    updates.append(update)

            updates.extend(self._withhold_risk_below_floor())

            if not updates:
                logger.info(
                    "[STOCK_SCORES] Risk absolute z-score pass: no symbol's risk_score/"
                    "composite_score changed (expected on a repeat run with unchanged inputs - "
                    "this pass is a pure function of the raw stored stability_metrics/price_daily "
                    "columns, same idempotency property as update_momentum_sector_neutral_scores())."
                )
                return

            with _owner().DatabaseContext("write") as cur:
                # ::numeric/::boolean casts on the VALUES columns (added 2026-09-17, factor-
                # purity follow-up, live-caught: this UPDATE was crashing on EVERY real pipeline
                # run since `_withhold_risk_below_floor()` was added 2026-09-16 -
                # "psycopg2.errors.DatatypeMismatch: column "risk_score" is of type numeric but
                # expression is of type text", because `updates` now mixes real floats
                # (corrected symbols) with None (withheld symbols) in the same risk_score column
                # position - the identical mixed-None/float wrong-inferred-column-type psycopg2
                # gotcha already hit and fixed for quality_score (vqg_quality_batch.py) and
                # momentum_score (momentum_scoring.py's update_momentum_sector_relative_
                # mom_12_1()) when THEIR OWN withhold-below-floor passes were added, but never
                # ported here despite Risk's own withhold pass landing the very next day. Because
                # post_run() calls this method unguarded and its own exception handler re-raises
                # (RuntimeError), this single missing cast was aborting post_run() ENTIRELY
                # before update_value_multiples_percentiles/update_growth_sector_neutral_scores/
                # update_momentum_sector_relative_mom_12_1/update_market_cap_tilted_weights ever
                # ran - not just leaving risk_score stale, but the whole downstream pillar
                # correction chain for every scoring run since 2026-09-16. This is very likely
                # the root cause of "the right list of stocks per factor isn't coming through"
                # (user, 2026-09-17): closed-end funds/trusts (BTT, IGI, NXP, TVC, and 127 more
                # live-confirmed, non-operating-excluded but still-scored symbols) were sitting
                # at the top of risk_score because the ONE pass that would have withheld them
                # never successfully wrote its results.
                _owner().execute_values(
                    cur,
                    """
                    UPDATE stock_scores AS ss
                    SET risk_score = v.risk_score::numeric,
                        composite_score = v.composite_score::numeric,
                        components = v.components::jsonb,
                        data_completeness = v.data_completeness::numeric,
                        data_unavailable = v.data_unavailable::boolean,
                        updated_at = CURRENT_TIMESTAMP
                    FROM (VALUES %s) AS v(symbol, risk_score, composite_score, components,
                                           data_completeness, data_unavailable)
                    WHERE ss.symbol = v.symbol
                    """,
                    updates,
                    template="(%s, %s, %s, %s, %s, %s)",
                )
            logger.info(
                f"[STOCK_SCORES] Risk absolute z-score pass corrected "
                f"{len(updates)}/{len(rows)} symbols' risk_score/composite_score (post_run completed)"
            )
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            error_msg = f"Risk absolute z-score batch update failed - stock scores cannot be finalized: {e}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e

    def _withhold_risk_below_floor(
        self,
    ) -> list[tuple[str, float | None, float, str | None, float, bool]]:
        """Companion to update_risk_absolute_zscore_scores(): finds the COMPLEMENT of that
        method's own correction population - symbols with a real risk_score but ineligible for
        correction (below the liquidity floor, missing/data_unavailable stability_metrics, or
        excluded by NON_OPERATING_COMPANY_EXCLUSION_SQL_TEMPLATE) - and withholds risk_score
        (NULL) plus recomputes composite_score/data_completeness/data_unavailable to match,
        rather than leaving Pass 1's stale, potentially-mega-cap-calibrated curve value
        (`_vol_curve_score`/`_max_drawdown_curve_score` - see this module's own top-of-file
        docstring on how poorly those fixed breakpoints fit this universe) in place indefinitely.

        PORTED 2026-09-16 (factor-purity sweep - this exact bug class was already found and
        fixed for Quality (vqg_quality_batch.py's `_withhold_quality_below_floor`) and Momentum
        (momentum_scoring.py's `_withhold_momentum_below_floor`, commit c1a3dd899) but never
        ported here or to Growth/Value - see those two methods' own docstrings for the shared
        rationale. Same gap, same fix, same shape.

        Returns tuples in the same (symbol, risk_score, composite_score, components,
        data_completeness, data_unavailable) shape update_risk_absolute_zscore_scores()'s own
        `updates` list uses, so the caller can extend one batch UPDATE with both.
        """
        with _owner().DatabaseContext("write") as cur:
            cur.execute(
                """
                SELECT ss.symbol, ss.composite_score, ss.quality_score, ss.growth_score,
                       ss.value_score, ss.momentum_score, ss.components,
                       ss.data_completeness, ss.data_unavailable
                FROM stock_scores ss
                JOIN stock_symbols su ON su.symbol = ss.symbol
                LEFT JOIN company_info_sec cis ON cis.symbol = ss.symbol
                LEFT JOIN stability_metrics sm ON sm.symbol = ss.symbol
                LEFT JOIN (
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
                ) liq_floor ON liq_floor.symbol = ss.symbol
                WHERE ss.risk_score IS NOT NULL
                  AND (
                        liq_floor.latest_close IS NULL
                        OR liq_floor.latest_close < %s
                        OR liq_floor.avg_dollar_volume_20d IS NULL
                        OR liq_floor.avg_dollar_volume_20d < %s
                        OR sm.symbol IS NULL
                        OR COALESCE(sm.data_unavailable, false) = true
                        OR NOT ("""
                + NON_OPERATING_COMPANY_EXCLUSION_SQL_TEMPLATE.format(symbols_alias="su", company_info_alias="cis")
                + """)
                  )
                """,
                (
                    getattr(self, "_min_stock_price", None) or DEFAULT_MIN_STOCK_PRICE,
                    getattr(self, "_min_adv_dollars", None) or DEFAULT_MIN_ADV_DOLLARS,
                ),
            )
            rows = cur.fetchall()

        if not rows:
            return []

        min_completeness_threshold = getattr(self, "_min_completeness_threshold", 70.0)
        withheld: list[tuple[str, float | None, float, str | None, float, bool]] = []
        for (
            symbol,
            _composite_score_old,
            quality_score,
            growth_score,
            value_score,
            momentum_score,
            components_old,
            _dc_old,
            _du_old,
        ) in rows:
            # GROWTH RESTORED TO COMPOSITE 2026-09-17 (same-day reversal - see
            # pillar_weights.py's BASE_PILLAR_WEIGHTS "ABOVE DECISION SUPERSEDED" note).
            weights = BASE_PILLAR_WEIGHTS
            pillar_scores = (
                ("quality", quality_score),
                ("value", value_score),
                ("momentum", momentum_score),
                ("growth", growth_score),
            )
            composite_val = sum(float(s) * weights[p] for p, s in pillar_scores if s is not None)
            composite_score_new = round(max(0.0, min(100.0, composite_val)), 2)
            available_weight = sum(weights[p] for p, s in pillar_scores if s is not None)
            data_completeness_new = min(99.99, round(available_weight * 100, 2))
            data_unavailable_new = data_completeness_new < min_completeness_threshold
            components_json = self._components_with_corrected_risk(components_old, None)
            withheld.append(
                (
                    symbol,
                    None,
                    composite_score_new,
                    components_json,
                    data_completeness_new,
                    data_unavailable_new,
                )
            )
        logger.info(
            f"[STOCK_SCORES] Risk: withheld risk_score for {len(withheld)} symbols below the "
            f"liquidity floor / excluded from the scoring population (never reached by the "
            f"correction pass above) - see _withhold_risk_below_floor's docstring."
        )
        return withheld
