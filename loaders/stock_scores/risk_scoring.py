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
"""

import itertools
import logging
import math
from typing import TYPE_CHECKING, Any

from utils.type_conversion import safe_float

logger = logging.getLogger("loaders.load_stock_scores")

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

        MINIMUM DATA REQUIREMENT: available weight (volatility_60d 0.45 + volatility_252d 0.15 +
        beta 0.15 + max_drawdown_1y 0.10 + avg_dollar_volume_20d/Liquidity 0.15, current as of
        the 2026-09-01 Liquidity reweight - see that field's own docstring below) must reach
        RISK_MIN_WEIGHT_AVAILABLE (0.40) - see that constant's own docstring for why a single
        thin field (e.g. max_drawdown_1y alone) is no longer enough. If all stability metrics
        are None, returns data_unavailable marker.
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
            weighted_sum += v60_score * 0.45
            total_weight += 0.45

        if not price_stats_unreliable and metrics.get("volatility_252d") is not None:
            v252_score = self._vol_curve_score(max(0, metrics["volatility_252d"]))
            weighted_sum += v252_score * 0.15
            total_weight += 0.15

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
            weighted_sum += beta_score * 0.15
            total_weight += 0.15

        # Max drawdown (1y): peak-to-trough decline, stored as a negative percentage
        # (e.g. -34.63 = a 34.63% decline from peak). Distinct signal from volatility (a
        # stock can have low day-to-day volatility yet still suffer one deep sustained
        # drawdown). Scored as a loss-severity characterization, not a return-prediction bet -
        # see this method's docstring for why (not stably predictive either direction).
        if metrics.get("max_drawdown_1y") is not None:
            drawdown_pct = abs(min(0.0, metrics["max_drawdown_1y"]))
            dd_score = self._max_drawdown_curve_score(drawdown_pct)
            weighted_sum += dd_score * 0.10
            total_weight += 0.10

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
            weighted_sum += liq_score * 0.15
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
