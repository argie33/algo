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

DELIBERATELY NOT given a SECTOR-neutral z-score batch pass (2026-09-13: a same-day Momentum
equivalent, `momentum_scoring.py`'s `update_momentum_sector_neutral_scores()`, was added then
reverted per a pre-existing FM/IC rejection - see load_stock_scores.py's post_run() NOTE).
Investigated directly before deciding, not assumed: this pillar's live sector averages DO diverge (Real Estate/
Utilities score safest ~60/59, Technology least-safe ~36, per that session's live DB check) -
the same shape of divergence that justified Momentum's rewrite. The difference is what the
divergence MEANS. Momentum's raw inputs are classic cross-sectional relative-strength measures
- the momentum anomaly (Jegadeesh 1990/Jegadeesh-Titman 1993/Carhart 1997) is defined and
academically harvested RELATIVE to peers, so an un-neutralized sector tilt is exactly the
"disguised sector bet" failure mode Barra/MSCI sector-neutralize momentum to prevent. Risk's
inputs here (volatility, max drawdown) are ABSOLUTE risk-of-loss magnitudes, and the low-
volatility anomaly they're meant to capture (Ang et al. 2006; Frazzini & Pedersen 2014 "Betting
Against Beta"; MSCI Minimum Volatility methodology) is measured and harvested on an ABSOLUTE
basis in the literature, not sector-relative - a utility genuinely being less volatile than a
biotech, day to day, is real economic signal the factor is supposed to reward, not measurement
noise to normalize away the way an ill-fitting absolute breakpoint curve was for Quality/Growth/
Value's fundamental ratios. Sector-neutralizing Risk would force Utilities and Technology to the
same average "safety" score by construction, destroying the exact signal this pillar exists to
capture. Beta is a second, independent reason it wouldn't fit this pillar's existing mechanism
even if the above didn't apply: it's already scored as distance-from-1.0 for market-correlated
swing-trading fit (see `_score_risk`'s own docstring), not as a return predictor - sector-
neutralizing a "closeness to 1.0" target would change what the score means, not just how it's
calibrated. Liquidity (avg_dollar_volume_20d) is a third: its curve is deliberately anchored to
`algo_config.min_adv_dollars` ($500K), this system's own absolute, non-sector-relative execution
gate - sector-relativizing it would break that anchor's entire rationale. Not re-litigated
without new evidence that contradicts the academic distinction above; if that evidence ever
shows up, redo this analysis rather than assume Momentum's fix generalizes automatically.

ABSOLUTE (non-sector) z-score batch pass ADDED 2026-09-13 (same session, immediately following
the reasoning above) for Volatility 60D/252D/Max Drawdown ONLY - a narrower, different fix from
the sector-neutral one just rejected. `_vol_curve_score`/`_max_drawdown_curve_score`'s fixed
breakpoints (0.15/0.30/0.60 for vol, 10/25/50 for drawdown) were live-checked against this
universe's actual distribution (stability_metrics, 4,920-4,996 scored symbols) rather than
trusted as calibrated: p50 volatility_60d=0.516 (the MEDIAN stock is already past the curve's
0.30 breakpoint, deep in the 50->10 decay segment) and p50 max_drawdown_1y=41.6% (already past
the drawdown curve's 25% breakpoint). Fewer than 1% of the universe clears vol_60d<=0.15 (the
curve's OWN 100-point threshold) - these breakpoints look tuned to a mega-cap-only mental model
of "normal" volatility, not this universe's real small/micro-cap-heavy composition, and unlike
Momentum's old Pass-1 curves (which get fully overwritten by that pillar's own sector-neutral
pass and never reach production), this pillar has no second pass - `_vol_curve_score`'s output
IS the live risk_score. `update_risk_absolute_zscore_scores()` below replaces just the TRANSFORM
for these 3 inputs (winsorize -> z-score -> normal-CDF-to-percentile against the live universe,
via the same `sector_neutral_zscore`/`zscore_to_percentile_scale` primitives Momentum/Growth/
Value already use, called with an empty sector map so every symbol pools into one universe-wide
group instead of being split by sector - preserving the deliberate non-sector-neutral design
above while fixing the curve-shape miscalibration) - matching what MSCI/S&P/AQR/FTSE Russell all
independently do for every factor (winsorize+z-score, not a hand-drawn absolute curve), the
same self-calibrating-to-the-live-distribution property Momentum/Growth/Value's z-score passes
already have and this pillar's fixed breakpoints never did. Beta (scored for closeness to 1.0,
not "lower is better" - not a z-score candidate at all, see above) and Liquidity (curve anchored
to a real system constant, not an invented breakpoint) are UNCHANGED, kept on their existing
curves.

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

import itertools
import json
import logging
import math
from typing import TYPE_CHECKING, Any

import psycopg2

from loaders.helpers.factor_normalization import sector_neutral_zscore, zscore_to_percentile_scale
from loaders.stock_scores.pillar_weights import BASE_PILLAR_WEIGHTS, _value_risk_adjusted_weights
from utils.loaders.helpers import NON_OPERATING_COMPANY_EXCLUSION_SQL_TEMPLATE
from utils.type_conversion import safe_float

logger = logging.getLogger("loaders.load_stock_scores")

# MIN_TRADING_DAYS_FOR_DRAWDOWN (added 2026-09-13, same session - see this module's own docstring
# "MIN_TRADING_DAYS_FOR_DRAWDOWN gate" note for the full live-verified evidence trail: brand-new
# IPOs with 5-55 days of history were landing in the top 15 of the corrected risk_score purely off
# max_drawdown_1y (populated over whatever partial history exists) + Liquidity, with
# volatility_60d/beta both correctly NULL for insufficient history. 60 matches
# volatility_60d's own minimum window - not a new number invented for this gate.
MIN_TRADING_DAYS_FOR_DRAWDOWN = 60


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

    def _score_risk(self, metrics: dict[str, Any] | None, symbol: str) -> float | dict[str, Any]:
        """Score risk metrics on 0-100 scale using price volatility / risk-of-loss signals only.

        UNIFORM EQUAL-WEIGHT (2026-09-11, user directive - see pillar_weights.py's
        BASE_PILLAR_WEIGHTS comment for the full rationale): the magnitude-tuned 45/15/15/10/15
        split documented below traced to the same isolated-backtest/contaminated-FM-data family
        that forced Growth and Value off similar weighting. All 5 components (Volatility 60D,
        Volatility 252D, Beta, Max Drawdown 1Y, Liquidity) are now flat 20% each. The component
        LIST and every curve/gate below (NEAR_ZERO_LIQUIDITY_THRESHOLD, the beta sign fix, the
        max_drawdown sign guard) are unchanged - only the combination weights are. The historical
        reasoning below is kept as the audit trail, not as justification for today's live weights.

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

        NEAR-ZERO-LIQUIDITY PRICE-STAT GATE, ADDED 2026-09-01 (see NEAR_ZERO_LIQUIDITY_THRESHOLD's
        own docstring): volatility_60d/volatility_252d/beta are skipped (weight not counted) when
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

        MINIMUM DATA REQUIREMENT: available weight (volatility_60d/volatility_252d/beta/
        max_drawdown_1y/Liquidity, each 0.20 post-2026-09-11 UNIFORM EQUAL-WEIGHT - the
        0.45/0.15/0.15/0.10/0.15 split this line once described is stale, not live) must
        reach RISK_MIN_WEIGHT_AVAILABLE (0.40, i.e. >=2 of the 5 components). If all
        stability metrics are None, returns data_unavailable marker.
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

        # NEAR_ZERO_LIQUIDITY_THRESHOLD gate (see that constant's own docstring): a near-zero
        # or frozen-price series makes volatility_60d/volatility_252d/beta measurement noise,
        # not a real signal - skip their weight here rather than trust a fabricated "calm"
        # reading. Only gates when avg_dollar_volume_20d is actually known; missing liquidity
        # data doesn't imply thin trading, so it leaves these inputs untouched.
        adv20 = metrics.get("avg_dollar_volume_20d")
        price_stats_unreliable = adv20 is not None and 0 <= adv20 < NEAR_ZERO_LIQUIDITY_THRESHOLD

        if not price_stats_unreliable and metrics.get("volatility_60d") is not None:
            v60_score = self._vol_curve_score(max(0, metrics["volatility_60d"]))
            weighted_sum += v60_score * 0.20
            total_weight += 0.20

        if not price_stats_unreliable and metrics.get("volatility_252d") is not None:
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
        if not price_stats_unreliable and metrics.get("beta") is not None:
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
        raw_max_drawdown = metrics.get("max_drawdown_1y")
        if raw_max_drawdown is not None:
            # REAL-MONEY-READINESS FIX (2026-09-10, financial-calc integrity audit):
            # `abs(min(0.0, raw_max_drawdown))` silently treated a positive/corrupted value
            # (e.g. a future writer storing an unsigned magnitude instead of this column's
            # documented negative-percentage convention) as a real 0.0 drawdown - the best
            # possible score, with no warning. load_risk_metrics_daily.py's own
            # _calculate_max_drawdown() can only ever return strictly negative or None today,
            # so this hasn't fired in practice, but this pillar must not silently reward what
            # would actually be a data-integrity violation if that producer ever changed.
            if raw_max_drawdown > 0:
                logger.critical(
                    f"[RISK SCORING] {symbol}: max_drawdown_1y={raw_max_drawdown} is positive - "
                    f"this column's convention is a negative percentage (peak-to-trough decline). "
                    f"Treating as a data-integrity violation, excluding from Risk score rather than "
                    f"scoring as a favorable (zero) drawdown."
                )
            else:
                drawdown_pct = abs(raw_max_drawdown)
                dd_score = self._max_drawdown_curve_score(drawdown_pct)
                weighted_sum += dd_score * 0.20
                total_weight += 0.20

        # Liquidity (20-trading-day average dollar volume), ADDED 2026-09-01 (goal session -
        # user directive after live-observing untradeable micro-cap banks topping Risk's
        # "safest" list: HYNE/PROV/QNBC all sit below algo_config's own min_adv_dollars=$500K
        # trade-eligibility floor, meaning a stock could rank near the top of "safest" while
        # being genuinely un-tradeable per this system's OWN downstream execution gate - the
        # scoring layer had no concept of tradability at all, only a disconnected pass/fail
        # gate applied much later in Phase 7/8, well after ranking already happened).
        #
        # Deliberately NOT the academic illiquidity-return-PREMIUM direction (Amihud 2002:
        # illiquid stocks earn HIGHER expected returns as compensation - this codebase's own
        # algo/research/fama_macbeth_liquidity_factor.py already tested and confirmed that
        # direction, t=3.34, real and distinct from size). Rewarding illiquidity would be
        # exactly backwards for this input's purpose here: that academic premium compensates a
        # BUY-AND-HOLD investor for tolerating years of hard-to-exit risk, but every other Risk
        # input in this pillar is explicitly scored for swing-trading fit (see Beta's own note
        # above - market-correlated-not-alpha, same non-return-predictive standard), where an
        # investor needs to enter AND exit within days-to-weeks. For that horizon, thin volume
        # is unambiguously a cost (wide spreads, slippage, can't size a position without moving
        # the price) - liquidity RISK, not an academic factor to harvest. Same non-alpha
        # design-choice footing as Beta, not a contradiction of the illiquidity-premium finding.
        #
        # Curve anchored to real, already-trusted numbers rather than an invented threshold:
        # breakpoints in log10(dollar_volume) space, piecewise-linear like this file's other
        # curves (_vol_curve_score/_margin_curve style) - $100K->0 (can't realistically trade
        # at all), $500K->35 (exactly algo_config.min_adv_dollars, this system's OWN existing
        # trade-eligibility floor - below this a stock would fail Phase 7/8's liquidity gate
        # outright, so it shouldn't score above marginal here either), $2M->65, $10M->90,
        # $50M+->100 (saturates - no further scoring benefit to being more liquid than that).
        if metrics.get("avg_dollar_volume_20d") is not None and metrics["avg_dollar_volume_20d"] > 0:
            liq_score = self._liquidity_curve_score(metrics["avg_dollar_volume_20d"])
            weighted_sum += liq_score * 0.20
            total_weight += 0.20

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

    @staticmethod
    def _liquidity_curve_score(avg_dollar_volume_20d: float) -> float:
        """Tradability-risk score for 20-trading-day average dollar volume. See _score_risk's
        liquidity-component docstring for the full rationale and why the breakpoints are
        anchored to algo_config.min_adv_dollars ($500K) rather than an invented number.
        `avg_dollar_volume_20d` must already be positive (callers guard via `> 0`).

        Piecewise-linear on log10(dollar_volume), same style as `_vol_curve_score`/
        `_max_drawdown_curve_score`: $100K->0, $500K->35 (the trade-eligibility floor itself),
        $2M->65, $10M->90, $50M+->100 (saturates).
        """
        log_dv = math.log10(avg_dollar_volume_20d)
        breakpoints = [(5.0, 0.0), (5.7, 35.0), (6.3, 65.0), (7.0, 90.0), (7.7, 100.0)]
        if log_dv <= breakpoints[0][0]:
            return 0.0
        if log_dv >= breakpoints[-1][0]:
            return 100.0
        for (x0, y0), (x1, y1) in itertools.pairwise(breakpoints):
            if log_dv <= x1:
                return y0 + (log_dv - x0) / (x1 - x0) * (y1 - y0)
        return 100.0  # unreachable - satisfies mypy's exhaustiveness check

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
        lifetime - this method runs as an independent, self-contained batch pass. Also counts
        each symbol's total real price_daily rows (`trading_days_history`) - see
        MIN_TRADING_DAYS_FOR_DRAWDOWN's own docstring for why max_drawdown_1y needs this gate."""
        with _owner().DatabaseContext("write") as cur:
            cur.execute(
                """
                WITH liquidity AS (
                    SELECT symbol, AVG(volume * close) AS avg_dollar_volume_20d
                    FROM (
                        SELECT symbol, volume, close,
                               ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY date DESC) AS rn
                        FROM price_daily
                        WHERE date >= CURRENT_DATE - INTERVAL '45 days'
                          AND COALESCE(data_unavailable, false) = false
                          AND volume IS NOT NULL AND close IS NOT NULL
                    ) ranked
                    WHERE rn <= 20
                    GROUP BY symbol
                ),
                history AS (
                    SELECT symbol, COUNT(*) AS trading_days_history
                    FROM price_daily
                    WHERE COALESCE(data_unavailable, false) = false
                    GROUP BY symbol
                )
                SELECT ss.symbol, ss.risk_score, ss.composite_score, ss.quality_score,
                       ss.growth_score, ss.value_score, ss.momentum_score, ss.components,
                       ss.data_completeness, ss.data_unavailable,
                       sm.volatility_60d, sm.volatility_252d, sm.beta, sm.max_drawdown_1y,
                       liq.avg_dollar_volume_20d, COALESCE(hist.trading_days_history, 0)
                FROM stock_scores ss
                JOIN stability_metrics sm ON sm.symbol = ss.symbol
                LEFT JOIN liquidity liq ON liq.symbol = ss.symbol
                LEFT JOIN history hist ON hist.symbol = ss.symbol
                JOIN stock_symbols su ON su.symbol = ss.symbol
                LEFT JOIN company_info_sec cis ON cis.symbol = ss.symbol
                WHERE ss.risk_score IS NOT NULL
                  AND COALESCE(sm.data_unavailable, false) = false
                  AND ("""
                + NON_OPERATING_COMPANY_EXCLUSION_SQL_TEMPLATE.format(symbols_alias="su", company_info_alias="cis")
                + ")"
            )
            rows: list[tuple[Any, ...]] = cur.fetchall()
            return rows

    @staticmethod
    def _compute_risk_absolute_zscore_percentiles(
        rows: list[tuple[Any, ...]],
    ) -> dict[str, dict[str, float]]:
        """Winsorize+z-score Risk's 3 "lower raw value is better" inputs (volatility_60d,
        volatility_252d, max_drawdown_1y magnitude) UNIVERSE-WIDE (no sector grouping - calling
        `sector_neutral_zscore` with an empty sector map pools every symbol into its single
        residual group, giving the plain winsorize-then-z-score this module's own docstring
        explains Risk needs INSTEAD of the sector-relative version Momentum/Growth/Value use).
        Split out of `update_risk_absolute_zscore_scores` for C901, pure function of its inputs.

        Each raw value is NEGATED before z-scoring so a symbol with a LOW volatility/drawdown -
        the desirable direction for this pillar - gets a HIGH z-score and therefore a HIGH
        percentile score, matching `zscore_to_percentile_scale`'s "higher input -> higher
        output" convention (used as-is, un-negated, by Momentum's own z-score pass, where higher
        raw momentum genuinely IS the desirable direction).

        Same NEAR_ZERO_LIQUIDITY_THRESHOLD measurement-validity gate `_score_risk` applies to
        volatility_60d/252d (not max_drawdown, which that gate never covered): a frozen/near-
        frozen-price symbol's mechanically-suppressed near-zero volatility is excluded from the
        population entirely here, not just from its own score - including it would bias every
        OTHER symbol's z-score against a fabricated data point, not just fail to score the thin
        symbol itself. max_drawdown_1y gets its OWN, separate MIN_TRADING_DAYS_FOR_DRAWDOWN gate
        (see that constant's docstring) for the same population-bias reason: a brand-new IPO's
        artificially-tiny drawdown (not enough elapsed time to have lived through a real one)
        would otherwise skew every other symbol's drawdown z-score too, not just its own.
        """
        raw_vol60: dict[str, float] = {}
        raw_vol252: dict[str, float] = {}
        raw_drawdown: dict[str, float] = {}

        for row in rows:
            symbol = row[0]
            vol_60d, vol_252d, _beta, max_drawdown_1y, adv20, trading_days_history = (
                row[10],
                row[11],
                row[12],
                row[13],
                row[14],
                row[15],
            )
            price_stats_unreliable = adv20 is not None and 0 <= float(adv20) < NEAR_ZERO_LIQUIDITY_THRESHOLD
            if not price_stats_unreliable:
                if vol_60d is not None:
                    raw_vol60[symbol] = -max(0.0, float(vol_60d))
                if vol_252d is not None:
                    raw_vol252[symbol] = -max(0.0, float(vol_252d))
            if (
                max_drawdown_1y is not None
                and float(max_drawdown_1y) <= 0
                and int(trading_days_history) >= MIN_TRADING_DAYS_FOR_DRAWDOWN
            ):
                raw_drawdown[symbol] = -abs(float(max_drawdown_1y))

        empty_sectors: dict[str, str] = {}
        return {
            "vol_60d": zscore_to_percentile_scale(sector_neutral_zscore(raw_vol60, empty_sectors)),
            "vol_252d": zscore_to_percentile_scale(sector_neutral_zscore(raw_vol252, empty_sectors)),
            "max_drawdown": zscore_to_percentile_scale(sector_neutral_zscore(raw_drawdown, empty_sectors)),
        }

    def _recompute_risk_row(
        self,
        row: tuple[Any, ...],
        pct_by_field: dict[str, dict[str, float]],
        min_completeness_threshold: float,
    ) -> tuple[str, float | None, float, str | None, float, bool] | None:
        """Recompute one symbol's risk_score/composite_score from the absolute z-score
        percentiles (Volatility 60D/252D/Max Drawdown) plus Beta/Liquidity's UNCHANGED existing
        curve scores, and diff against its current stored values. Returns None if nothing
        changed. Split out of `update_risk_absolute_zscore_scores` for C901, pure function of
        its inputs - mirrors MomentumScoringMixin._recompute_momentum_row's structure."""
        symbol = row[0]
        risk_score_old = float(row[1])
        composite_score_old = float(row[2])
        quality_score, growth_score, value_score, momentum_score = row[3], row[4], row[5], row[6]
        components_old = row[7]
        data_completeness_old = float(row[8]) if row[8] is not None else None
        data_unavailable_old = bool(row[9]) if row[9] is not None else False
        beta, max_drawdown_1y, adv20, trading_days_history = row[12], row[13], row[14], row[15]

        price_stats_unreliable = adv20 is not None and 0 <= float(adv20) < NEAR_ZERO_LIQUIDITY_THRESHOLD

        weighted_sum = 0.0
        total_weight = 0.0
        if symbol in pct_by_field["vol_60d"]:
            weighted_sum += pct_by_field["vol_60d"][symbol] * 0.20
            total_weight += 0.20
        if symbol in pct_by_field["vol_252d"]:
            weighted_sum += pct_by_field["vol_252d"][symbol] * 0.20
            total_weight += 0.20
        if not price_stats_unreliable and beta is not None:
            diff = min(abs(float(beta) - 1.0), 2.0)
            weighted_sum += max(0.0, 100 - (diff * 50)) * 0.20
            total_weight += 0.20
        if symbol in pct_by_field["max_drawdown"]:
            weighted_sum += pct_by_field["max_drawdown"][symbol] * 0.20
            total_weight += 0.20
        elif max_drawdown_1y is not None and float(max_drawdown_1y) > 0:
            logger.critical(
                f"[RISK SCORING] {symbol}: max_drawdown_1y={max_drawdown_1y} is positive in the "
                f"absolute z-score pass - data-integrity violation, excluding from Risk score "
                f"(same guard _score_risk's Pass-1 curve applies)."
            )
        elif max_drawdown_1y is not None and int(trading_days_history) < MIN_TRADING_DAYS_FOR_DRAWDOWN:
            logger.debug(
                f"[STOCK_SCORES] {symbol} max_drawdown_1y excluded from absolute z-score pass: "
                f"only {trading_days_history} trading days of history, below "
                f"MIN_TRADING_DAYS_FOR_DRAWDOWN={MIN_TRADING_DAYS_FOR_DRAWDOWN} - not enough "
                f"elapsed time for this reading to reflect a real drawdown."
            )
        if adv20 is not None and float(adv20) > 0:
            weighted_sum += self._liquidity_curve_score(float(adv20)) * 0.20
            total_weight += 0.20

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

        weights = _value_risk_adjusted_weights(risk_score_new)
        composite_val = 0.0
        for pillar_name, pillar_score in (
            ("quality", quality_score),
            ("growth", growth_score),
            ("value", value_score),
            ("risk", risk_score_new),
            ("momentum", momentum_score),
        ):
            if pillar_score is not None:
                composite_val += float(pillar_score) * weights[pillar_name]
        composite_score_new = round(max(0.0, min(100.0, composite_val)), 2)

        all_scores_new: dict[str, float | None] = {
            "quality": float(quality_score) if quality_score is not None else None,
            "growth": float(growth_score) if growth_score is not None else None,
            "value": float(value_score) if value_score is not None else None,
            "risk": risk_score_new,
            "momentum": float(momentum_score) if momentum_score is not None else None,
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
        real winsorize+z-score against the current run's universe for Volatility 60D/252D/Max
        Drawdown, then FULLY RECOMPUTES risk_score and composite_score from scratch off the raw
        stored stability_metrics/price_daily columns - mirrors
        `update_momentum_sector_neutral_scores()`'s pure-overwrite pattern, with one deliberate
        difference: no sector grouping (see this module's own docstring for why Risk stays
        universe-wide rather than sector-relative like Momentum/Growth/Value), and a
        MIN_TRADING_DAYS_FOR_DRAWDOWN gate on max_drawdown_1y that Pass 1 does not have (found
        during this pass's own pre-ship verification - see that constant's docstring).

        WHY (2026-09-13, /goal "question the scoring methodology" session): live-checked
        `_vol_curve_score`'s breakpoints (0.15/0.30/0.60) against the real stability_metrics
        distribution before touching anything - p50 volatility_60d=0.516, already past the
        curve's OWN 0.30 breakpoint (the point where its score formula switches to the steepest
        decay segment), and under 1% of the universe clears the curve's 100-point threshold
        (0.15). Same story for `_max_drawdown_curve_score` (p50 max_drawdown_1y=41.6%, past its
        25% breakpoint). These breakpoints were never derived from this universe's actual
        distribution - fixing that (self-calibrating winsorize+z-score, recomputed fresh every
        run against whatever the universe currently looks like) is the same fix already applied
        to Momentum/Growth/Value's analogous absolute-mapping problem, using the same shared
        primitive (`sector_neutral_zscore`/`zscore_to_percentile_scale`), just without the
        sector grouping those three use (this pillar's own docstring already explains why: the
        low-volatility anomaly - Ang et al. 2006, Frazzini & Pedersen 2014 - is harvested on an
        ABSOLUTE basis in the literature, not sector-relative, so sector-neutralizing it would
        destroy the exact signal this pillar exists to capture).

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

        Beta and Liquidity are UNCHANGED - recomputed here using their existing, unmodified
        curve functions (`_liquidity_curve_score`) or inline formula (beta's distance-from-1.0),
        purely so this pass can fully recompute risk_score/composite_score without depending on
        Pass-1's now-partially-stale value. Beta isn't a "lower is better" input at all (it's
        scored for closeness to 1.0, a different kind of target the z-score transform doesn't
        fit), and Liquidity's curve is already anchored to a real system constant
        (`algo_config.min_adv_dollars`), not an invented breakpoint - neither has the
        miscalibration problem this pass exists to fix.

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

            if not updates:
                logger.info(
                    "[STOCK_SCORES] Risk absolute z-score pass: no symbol's risk_score/"
                    "composite_score changed (expected on a repeat run with unchanged inputs - "
                    "this pass is a pure function of the raw stored stability_metrics/price_daily "
                    "columns, same idempotency property as update_momentum_sector_neutral_scores())."
                )
                return

            with _owner().DatabaseContext("write") as cur:
                _owner().execute_values(
                    cur,
                    """
                    UPDATE stock_scores AS ss
                    SET risk_score = v.risk_score,
                        composite_score = v.composite_score,
                        components = v.components::jsonb,
                        data_completeness = v.data_completeness,
                        data_unavailable = v.data_unavailable,
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
