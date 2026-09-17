"""ValueScoreMixin._score_value, extracted from load_stock_scores.py (2026-09-05,
file-size-ratchet bloaters-decomposition split): this single method is ~830 of the file's
original ~4,510 lines - the largest single concentration, comparable to vqg_quality.py's
_compute_quality_metrics extraction the same day. Moved verbatim - no behavior change.

Kept in its own file, separate from the rest of the Value pillar (loaders/stock_scores/
value_metrics.py), purely because this one method alone is close to the file-size ratchet's
800-line new-file cap - splitting it further would mean breaking up its internal logic, a
materially different (and riskier) change than a mechanical, behavior-preserving move.

Mixed into StockScoresLoader alongside the other stock_scores/*.py pillar mixins - every
`self.` reference here resolves normally through the instance regardless of which mixin file
defines it. This method does no database access of its own (pure computation over an
already-fetched metrics dict), so - unlike value_metrics.py's update_value_multiples_percentiles
- it needs no DatabaseContext/execute_values indirection.
"""

import logging
from typing import TYPE_CHECKING, Any

logger = logging.getLogger("loaders.load_stock_scores")

# VALUE_MIN_WEIGHT (added 2026-09-07, /goal session: "dig into the scoring results" sweep).
# _score_value's `if total_weight > 0: return weighted_sum / total_weight` accepted ANY nonzero
# weight as a fully-confident score - live-verified this lets a single satellite input produce
# a value_score indistinguishable in the DB from a name scored off real coverage of PE/PB/PS.
# This is the identical thin-sample-extrapolation problem Growth (GROWTH_MIN_FIELDS_AVAILABLE,
# ~42% of its 12 fields - see growth_scoring.py) and Quality (40-point floor out of a 101-point
# nominal total - see quality_scoring.py's own docstring) already solved for themselves; Value
# never got the same treatment. Below this, _score_value returns a data_unavailable marker
# instead of a score built from too little evidence, same principle, not a new one invented
# here.
#
# P/S AND DIVIDEND YIELD REMOVED FROM PASS-1 SCORING ENTIRELY (2026-09-16, factor-purity
# sweep - "get this perverse shit out of here... we want the purest factor scores in line with
# the industry guys"). These two inputs (plus the FCF-payout-sustainability gate and the
# hand-built dividend magnitude-bonus curve that only existed to score dividend_yield) had
# already been deleted from the REAL score on 2026-09-15, when Pass 2
# (value_metrics.update_value_multiples_percentiles) was rewritten to MSCI Enhanced Value's
# actual published 3-variable definition (Book/Price-or-Cash-Earnings/Price, Forward
# Earnings/Price, EV/CFO-or-Cash-Earnings/Price) - that methodology has "no home" for P/S or
# dividend yield at all, per that pass's own docstring. Pass 1 (this function) was never
# brought back in sync, so it kept computing and weighting both every single run - a fixed
# P/S curve, a hand-set "70 + 5-per-point, capped at 6% yield" dividend bonus, and a hand-set
# 1.0x/2.0x FCF-payout taper - entirely dead work with zero effect on the persisted score
# (Pass 2 always overwrites it), except in the one scenario where it isn't dead: if Pass 2
# ever fails partway through a run, a symbol is left holding THIS non-industry-standard,
# never-validated Pass-1 value as its real, persisted value_score. Deleted outright rather
# than resynced to Pass 2's percentile logic - Pass 1 only needs to be a safe interim value,
# not a second implementation of the real methodology to keep parallel-maintained forever.
# VALUE_MIN_WEIGHT's nominal max total_weight is now 0.60 (PE/PB/Forward-PE, 0.20 each) -
# still comfortably above this 0.40 floor whenever all three are present.
VALUE_MIN_WEIGHT = 0.40


class ValueScoreMixin:
    """See module docstring.

    `_pe_curve_score`/`_pb_curve_score` are defined on the sibling ValueMetricsMixin
    (loaders/stock_scores/value_metrics.py) - declared type-checking-only below so mypy can
    see them without a real circular import (both are mixed into the same StockScoresLoader,
    so `self.` resolves them fine at runtime either way). `_ps_curve_score` is intentionally
    NOT referenced here - see VALUE_MIN_WEIGHT's module docstring for why P/S was removed from
    scoring entirely (2026-09-16); it stays defined on ValueMetricsMixin only as a
    computed-but-unscored utility (value_metrics.py still displays the raw ps_ratio).
    """

    if TYPE_CHECKING:

        @staticmethod
        def _pe_curve_score(pe: float) -> float: ...

        @staticmethod
        def _pb_curve_score(pb: float) -> float: ...

    def _score_value(self, metrics: dict[str, Any] | None, symbol: str) -> float | dict[str, Any]:
        """Score value metrics on 0-100 scale. Returns marker dict if no real data.

        This is the Pass-1 PROVISIONAL scorer only. It scores PE/PB/Forward-PE with fixed
        piecewise curves (`_pe_curve_score`/`_pb_curve_score`, each 20% of a 0.60 nominal max
        weight - see VALUE_MIN_WEIGHT's module docstring) as a placeholder value. The REAL,
        live score is a cross-sectional percentile rank against the current run's universe,
        computed by `value_metrics.update_value_multiples_percentiles()` (post_run(), a batch
        pass that overwrites value_score/composite_score after every symbol has been scored)
        using MSCI Enhanced Value's actual 3-leg definition (Book/Price-or-Cash-Earnings/Price,
        Forward Earnings/Price, EV/CFO-or-Cash-Earnings/Price) - see that function's own
        docstring. This function's provisional value only ever persists as the real score if
        Pass 2 fails partway through a run.

        P/S and Dividend Yield are NOT scored here or in Pass 2 - MSCI Enhanced Value's real
        methodology has no home for either. PEG, FCF yield, Margin of Safety, Net Payout Yield,
        EV/EBITDA, EV/Revenue, Amihud illiquidity, and a standalone Size factor were all
        evaluated and removed from Value scoring over the course of this repo's history (each
        either duplicated an existing multiple, isn't part of any mainstream systematic Value
        construction, or didn't hold up under robustness testing) - see git history/PR
        descriptions for that evidence trail rather than this docstring.

        For the earnings-yield vs. P/E floor and other implementation notes, see the inline
        comments below.

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

        MINIMUM DATA REQUIREMENT: at least VALUE_MIN_WEIGHT (0.40) of nominal weight
        (PE 0.20 + PB 0.20 + Forward P/E 0.20 = 0.60) must be available - see that constant's
        own docstring. Below that, or if all value metrics are None, returns a data_unavailable
        marker rather than a thin-sample score.
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
        # approach over this repo's own in-sample-optimized weights (this 27/27/27/9/10 split
        # itself SUPERSEDED 2026-09-11 - see this method's top docstring, "UNIFORM
        # EQUAL-WEIGHT": all 5 inputs are flat 20% each below now; stale-comment/live-code
        # mismatch found 2026-09-13 scoring-accuracy audit).
        if metrics.get("pe_ratio") is not None and metrics["pe_ratio"] > 0:
            pe_score = self._pe_curve_score(metrics["pe_ratio"])
            weighted_sum += pe_score * 0.20
            total_weight += 0.20
        elif metrics.get("pe_ratio_unavailable_reason") == "unprofitable_stock":
            weighted_sum += 0.0 * 0.20
            total_weight += 0.20

        # P/B ratio: lower is better for value; < 3 is reasonable for most sectors.
        # NEGATIVE-BOOK-VALUE FLOOR ADDED 2026-09-05 (real-money-readiness audit): same bug
        # class and fix as the "UNPROFITABLE-COMPANY FLOOR"/"UNPROFITABLE-FORECAST FLOOR"
        # notes above for P/E and Forward P/E - negative stockholders' equity (distressed
        # leverage, LBO-style buybacks) makes pb_ratio mathematically undefined, and this was
        # previously just SKIPPED, renormalizing the Value pillar over PE/PS/Forward-PE/Dividend
        # as if the P/B component didn't exist rather than correctly scoring it at the floor.
        # A negative book value is definitionally worse than any positive one on a book-to-
        # market basis, so flooring at 0 (this pillar's existing "worst" value, matching
        # `_pb_curve_score`'s own floor) is the correct treatment - same reasoning already
        # applied to P/E's `unprofitable_stock` and Forward P/E's `negative_forward_eps` cases.
        if metrics.get("pb_ratio") is not None and metrics["pb_ratio"] > 0:
            pb_score = self._pb_curve_score(metrics["pb_ratio"])
            weighted_sum += pb_score * 0.20
            total_weight += 0.20
        elif metrics.get("pb_ratio_unavailable_reason") == "negative_book_value":
            weighted_sum += 0.0 * 0.20
            total_weight += 0.20

        # P/S ratio - REMOVED FROM PASS-1 SCORING 2026-09-16 (factor-purity sweep - see
        # VALUE_MIN_WEIGHT's module docstring). MSCI Enhanced Value's real published
        # definition has no P/S leg at all; Pass 2 already dropped it entirely on 2026-09-15.
        # ps_ratio stays fully computed/stored/displayed (value_metrics.ps_ratio) - same
        # "computed but unscored" convention as ev_ebitda/ev_revenue elsewhere in this file.

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
            weighted_sum += fwd_pe_score * 0.20
            total_weight += 0.20
        elif metrics.get("forward_pe_unavailable_reason") == "negative_forward_eps":
            weighted_sum += 0.0 * 0.20
            total_weight += 0.20

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

        # Dividend yield - REMOVED FROM PASS-1 SCORING 2026-09-16 (factor-purity sweep - see
        # VALUE_MIN_WEIGHT's module docstring). MSCI Enhanced Value's real published
        # definition has no dividend-yield leg; Pass 2 already dropped it entirely on
        # 2026-09-15, deleting its whole computation path (sustainability haircut, saturating
        # transform, sector-size-neutral z-score) as unconsumed dead work. This Pass-1 block -
        # the hand-set "70 base + 5-per-point, capped at 6% yield" bonus curve and the hand-set
        # 1.0x/2.0x FCF-payout-sustainability taper - was the last piece still computing and
        # weighting it, now removed to match. dividend_yield/net_payout_yield/fcf_yield all
        # stay fully computed/stored/displayed - same "computed but unscored" convention as
        # ev_ebitda/ev_revenue elsewhere in this file.

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

        if total_weight >= VALUE_MIN_WEIGHT:
            return weighted_sum / total_weight
        if total_weight > 0:
            logger.warning(
                f"[STOCK_SCORES] {symbol} value_score withheld: only {total_weight:.2f}/1.00 nominal "
                f"weight available, below VALUE_MIN_WEIGHT={VALUE_MIN_WEIGHT}. See that constant's "
                f"docstring - a single satellite input's weight is thin-sample extrapolation, not an "
                f"honest partial score."
            )
            return {
                "symbol": symbol,
                "data_unavailable": True,
                "reason": "insufficient_value_inputs_thin_sample",
            }
        logger.debug(f"[STOCK_SCORES] No value metrics found to score for {symbol}")
        logger.debug(
            f"[STOCK_SCORES] Returning data_unavailable marker for value_score({symbol}) - no scoreable fields"
        )
        return {"symbol": symbol, "data_unavailable": True, "reason": "no_value_scores_computed"}
