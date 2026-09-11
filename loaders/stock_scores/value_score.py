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
# weight as a fully-confident score - live-verified this lets a single satellite input (most
# often dividend_yield=0.0 for a non-dividend-paying stock, 10% of nominal weight, or the
# unprofitable-PE floor at 27%) produce a value_score indistinguishable in the DB from a name
# scored off real coverage of PE/PB/PS. Live sweep: 71 universe symbols currently get a
# value_score built from <=20% of nominal weight (17 from dividend_yield ALONE). This is the
# identical thin-sample-extrapolation problem Growth (GROWTH_MIN_FIELDS_AVAILABLE, ~42% of its
# 12 fields - see growth_scoring.py) and Quality (40-point floor out of a 101-point nominal
# total - see quality_scoring.py's own docstring) already solved for themselves; Value never
# got the same treatment. 0.40 mirrors that same ~40% convention against this pillar's own
# 1.00 nominal total (PE 0.27 + PB 0.27 + PS 0.27 + Forward P/E 0.09 + Dividend Yield 0.10).
# Below this, _score_value returns a data_unavailable marker instead of a score built from too
# little evidence, same principle, not a new one invented here.
VALUE_MIN_WEIGHT = 0.40

# DIVIDEND PAYOUT-SUSTAINABILITY GATE (added 2026-09-08, real-money-readiness audit: "does the
# dividend_yield term correctly penalize a high yield that's funded by negative FCF, or does it
# reward a value-trap the same as a genuinely cheap, well-covered dividend?"). Confirmed real
# gap: dividend_yield's scoring block (below) only ever looked at yield magnitude - a stock
# with a 21%+ yield funded entirely by negative free cash flow (a classic, well-documented
# value-trap pattern: the dividend is one downgrade/cut away from a price collapse) scored the
# SAME as an equally-high yield backed by strong FCF coverage. fcf_yield is already
# fetched into `metrics` (value_metrics.py's _get_value_metrics) but unused here - it was
# REMOVED as its own standalone scored input 2026-08-28 ("FCF YIELD - RESOLVED" docstring note
# below) because it was robustly WRONG-SIGNED as an independent cheapness signal (higher
# fcf_yield predicted LOWER forward returns). That finding does not apply here: this is not
# re-adding fcf_yield as an alpha input, it's using it as a risk GATE on a different input
# (dividend_yield) - conceptually distinct, same way this pillar already treats
# "unprofitable_stock"/"negative_book_value" as floors on PE/PB rather than standalone inputs.
# Since dividend_yield and fcf_yield are both yield-on-price (dividends/price, fcf/price), their
# ratio is exactly the FCF payout ratio (dividends/FCF) with price canceling out - no new data
# needed. FCF_PAYOUT_UNSUSTAINABLE_RATIO=1.0: paying out 100%+ of FCF as dividends is the
# standard unsustainable-payout threshold (any coverage ratio below 1x means the dividend is
# funded by debt/asset sales/equity issuance, not organic cash generation). Below 1.0x: no
# penalty (this is what a well-covered dividend looks like). 1.0x-2.0x: linearly taper the
# dividend score to 0 (this file's existing "worst" floor value, see PE/PB's own floors) by
# 2.0x. Negative or zero FCF while paying any dividend at all is floored straight to 0 -
# unambiguously the worst case, not merely "high payout ratio" (division would give a
# meaningless negative "ratio" otherwise). Missing fcf_yield (no coverage available) leaves
# dividend_yield scored on magnitude alone, same fail-safe-on-missing-data convention as every
# other input in this pillar - this gate only fires when there's real evidence to fire on.
FCF_PAYOUT_UNSUSTAINABLE_RATIO = 1.0
FCF_PAYOUT_ZERO_SCORE_RATIO = 2.0


def _dividend_sustainability_factor(dividend_yield: float, fcf_yield: float | None) -> float:
    """Scale factor (0.0-1.0) to apply to the raw dividend_yield score.

    See FCF_PAYOUT_UNSUSTAINABLE_RATIO's module-level docstring for the full reasoning. Pure
    function, no I/O - dividend_yield/fcf_yield are both already-fetched value_metrics fields.
    """
    if dividend_yield <= 0 or fcf_yield is None:
        return 1.0
    if fcf_yield <= 0:
        # Dividend funded by negative (or zero) free cash flow - the classic value-trap
        # pattern (e.g. a stock scoring well on a double-digit yield that's actually being
        # paid out of debt/asset sales while operations burn cash). Unambiguously the worst
        # case - floor straight to 0 rather than computing a meaningless negative "ratio".
        return 0.0
    payout_ratio = dividend_yield / fcf_yield
    if payout_ratio <= FCF_PAYOUT_UNSUSTAINABLE_RATIO:
        return 1.0
    if payout_ratio >= FCF_PAYOUT_ZERO_SCORE_RATIO:
        return 0.0
    # Linear taper between 1.0x (fully covered, no penalty) and 2.0x (floor)
    span = FCF_PAYOUT_ZERO_SCORE_RATIO - FCF_PAYOUT_UNSUSTAINABLE_RATIO
    return 1.0 - (payout_ratio - FCF_PAYOUT_UNSUSTAINABLE_RATIO) / span


class ValueScoreMixin:
    """See module docstring.

    `_pe_curve_score`/`_pb_curve_score`/`_ps_curve_score` are defined on the sibling
    ValueMetricsMixin (loaders/stock_scores/value_metrics.py) - declared type-checking-only
    below so mypy can see them without a real circular import (both are mixed into the same
    StockScoresLoader, so `self.` resolves them fine at runtime either way).
    """

    if TYPE_CHECKING:

        @staticmethod
        def _pe_curve_score(pe: float) -> float: ...

        @staticmethod
        def _pb_curve_score(pb: float) -> float: ...

        @staticmethod
        def _ps_curve_score(ps: float) -> float: ...

    def _score_value(self, metrics: dict[str, Any] | None, symbol: str) -> float | dict[str, Any]:
        """Score value metrics on 0-100 scale. Returns marker dict if no real data.

        UNIFORM EQUAL-WEIGHT (2026-09-11, user directive - see pillar_weights.py's
        BASE_PILLAR_WEIGHTS comment for the full rationale): the 27/27/27/9/10 split below
        (already a move away from fully in-sample-optimized weights, see "EQUAL-WEIGHTED
        2026-09-01" note further down) is now flat 20% each across all 5 components (PE/PB/PS/
        Forward PE/Dividend Yield) - no more smaller "satellite" weights for Forward PE/Dividend
        Yield. value_metrics.py's update_value_multiples_percentiles() mirrors this exact split -
        keep both in sync if either changes. Historical reasoning below is kept as audit trail.

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

        MINIMUM DATA REQUIREMENT: at least VALUE_MIN_WEIGHT (0.40) of nominal weight
        (PE 0.27 + PB 0.27 + PS 0.27 + Forward P/E 0.09 + Dividend Yield 0.10 = 1.00) must be
        available - see that constant's own docstring. Below that, or if all value metrics are
        None, returns a data_unavailable marker rather than a thin-sample score.
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

        # P/S ratio: lower is better; thresholds sit higher than P/B since revenue
        # multiples run richer than book multiples (especially for growth/SaaS names).
        if metrics.get("ps_ratio") is not None and metrics["ps_ratio"] > 0:
            ps_score = self._ps_curve_score(metrics["ps_ratio"])
            weighted_sum += ps_score * 0.20
            total_weight += 0.20

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
            # PAYOUT-SUSTAINABILITY GATE - see FCF_PAYOUT_UNSUSTAINABLE_RATIO's module-level
            # docstring above. Penalizes (does not just cap) a high yield that isn't covered by
            # free cash flow - the CATO-pattern value trap this pillar previously scored
            # identically to a well-covered dividend of the same magnitude.
            div_score *= _dividend_sustainability_factor(metrics["dividend_yield"], metrics.get("fcf_yield"))
            weighted_sum += div_score * 0.20
            total_weight += 0.20

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
