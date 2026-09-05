"""Value pillar: `_get_value_metrics`/`_score_value`, extracted verbatim (no logic change)
from loaders/load_stock_scores.py. StockScoresLoader keeps same-name, same-signature instance
methods that delegate here.
"""

import logging
from typing import Any

from loaders.stock_scores import scoring_curves
from utils.type_conversion import safe_float

logger = logging.getLogger(__name__)


def _get_value_metrics(value_cache: dict[str, tuple[Any, ...]], symbol: str) -> dict[str, Any]:
    """Fetch value metrics for symbol.

    Returns explicit marker dict if data is unavailable (either no row or data_unavailable=True).
    Raises RuntimeError on database errors or data type mismatches.

    VALIDATION RULES:
    - Row length validation: Must have 15 columns (pe_ratio, pb_ratio, ps_ratio, peg_ratio,
      dividend_yield, fcf_yield, forward_pe, ev_ebitda, ev_revenue, margin_of_safety_pct,
      market_cap, net_payout_yield, pe_ratio_unavailable_reason,
      forward_pe_unavailable_reason, data_unavailable) - the two *_unavailable_reason
      columns distinguish "genuinely missing data" from "unprofitable company / negative
      earnings forecast" for P/E and Forward P/E (see _score_value's unprofitable-company
      floor docstring note).
    - Schema mismatch (len(row) < 15) → raises ValueError immediately
    - All numeric fields converted via safe_float() (detects data corruption)
    - data_unavailable=True flag → returns marker dict even if row exists (not NULLs)
    - No row at all → returns marker dict with reason="no_value_metrics_found"
    """
    row = value_cache.get(symbol)
    if row:
        # Validate row has expected 15 columns before accessing indices - see _score_value's
        # docstring for what each field beyond the original 11 is for.
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
    logger.warning(f"[LOAD_STOCK_SCORES] No value metrics available for {symbol} - score completeness will be reduced")
    return {"symbol": symbol, "data_unavailable": True, "reason": "no_value_metrics_found"}


def _score_value(metrics: dict[str, Any] | None, symbol: str) -> float | dict[str, Any]:
    """Score value metrics on 0-100 scale. Returns marker dict if no real data.

    P/E, P/B, and P/S are NOT genuinely scored by this function's fixed piecewise curves
    (`_pe_curve_score`/`_pb_curve_score`/`_ps_curve_score`) - those only provide a
    PROVISIONAL Pass-1 placeholder. The real score is a cross-sectional PERCENTILE RANK
    against the current run's universe, computed in `update_value_multiples_percentiles()`
    (post_run(), a batch pass that overwrites value_score/composite_score after every
    symbol has been scored) - the same two-phase provisional-then-corrected pattern this
    file's `update_rs_percentiles()` established for Momentum's rs_percentile. Cross-
    sectional percentile beats a fixed curve or time-series/hybrid approach on this repo's
    own history (see algo/research/value_absolute_curve_vs_relative_ranking_20260828.py).

    Current weighted scoring: P/E (27%) + P/B (27%) + P/S (27%) + Forward P/E (9%) +
    Dividend Yield (10%) - five scored inputs, no PEG, no Margin of Safety. The three core
    multiples are equal-weighted (industry-conventional, matching Fama-French HML / AQR
    composites) rather than skewed toward whichever backtested strongest on this repo's own
    sample. Forward P/E and Dividend Yield stay smaller satellite weights - thinner history
    and weaker evidence respectively, not "core" descriptors in mainstream methodologies.

    Inputs computed but deliberately NOT scored here (still fetched/displayed, same
    "computed-but-unscored" convention used elsewhere in this file):
    - PEG: growth-blended multiple: mainstream Value methodologies (Fama-French/MSCI/S&P/
      AQR) keep Value and Growth as separate factors, not blended.
    - EV/EBITDA, EV/Revenue: near-duplicates of P/E and P/S respectively (r=0.93/1.00 in
      this repo's data) - the incremental net-debt-wedge content they'd add is already
      captured by Quality's debt_to_equity, not a novel signal.
    - FCF yield: multivariate coefficient came back consistently wrong-signed (higher
      fcf_yield -> lower forward return) across every sample construction tested.
    - Margin of Safety / DCF discount to intrinsic value: an intrinsic-value/deep-value
      screening tool by industry convention, not treated as a systematic Value-factor input
      by mainstream index methodologies. Note: the underlying DCF caps forecast growth at
      15%/yr, so a hypergrowth name will structurally show a large negative margin of
      safety even with excellent fundamentals - a real, understood bias in that field, not
      a scoring bug (relevant if this input is ever revisited).
    - Amihud illiquidity: a real, validated signal (positive, reproducible), but literature
      classifies illiquidity as its own distinct risk factor family (Amihud 2002;
      Pastor-Stambaugh 2003), conceptually separate from value/cheapness - folding it into
      value_score would muddy what that score means.
    - Net Payout Yield: tested stronger than Dividend Yield, but Dividend Yield is used
      instead per explicit user direction (net_payout_yield stays computed/fetched).

    Forward P/E is a judgment-call inclusion, not evidence-based: analyst_earnings_estimates
    has too little historical depth to backtest (a live-only consensus-estimate snapshot,
    not vendor-backed history), included on institutional pedigree (MSCI Value uses 12-month
    forward E/P as a core descriptor) pending enough accumulated history to test it. Reuses
    `_pe_curve_score` as the Pass-1 provisional value and joins the same percentile-rank
    reconciliation as P/E/P/B/P/S.

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
        pe_score = scoring_curves._pe_curve_score(metrics["pe_ratio"])
        weighted_sum += pe_score * 0.27
        total_weight += 0.27
    elif metrics.get("pe_ratio_unavailable_reason") == "unprofitable_stock":
        weighted_sum += 0.0 * 0.27
        total_weight += 0.27

    # P/B ratio: lower is better for value; < 3 is reasonable for most sectors.
    if metrics.get("pb_ratio") is not None and metrics["pb_ratio"] > 0:
        pb_score = scoring_curves._pb_curve_score(metrics["pb_ratio"])
        weighted_sum += pb_score * 0.27
        total_weight += 0.27

    # P/S ratio: lower is better; thresholds sit higher than P/B since revenue
    # multiples run richer than book multiples (especially for growth/SaaS names).
    if metrics.get("ps_ratio") is not None and metrics["ps_ratio"] > 0:
        ps_score = scoring_curves._ps_curve_score(metrics["ps_ratio"])
        weighted_sum += ps_score * 0.27
        total_weight += 0.27

    # PEG removed from scoring: it's a growth-adjusted multiple, and mainstream systematic
    # Value methodologies (MSCI/Russell/S&P/Fama-French/AQR) keep Value and Growth as
    # separate factors, not blended - not a statistical rejection. peg_ratio stays
    # computed/stored (computed-but-unscored, like ev_ebitda/ev_revenue/fcf_yield/margin_of_safety).

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
        fwd_pe_score = scoring_curves._pe_curve_score(metrics["forward_pe"])
        weighted_sum += fwd_pe_score * 0.09
        total_weight += 0.09
    elif metrics.get("forward_pe_unavailable_reason") == "negative_forward_eps":
        weighted_sum += 0.0 * 0.09
        total_weight += 0.09

    # FCF yield REMOVED 2026-08-28 (see "FCF YIELD - RESOLVED 2026-08-28" docstring note
    # below): independently re-verified and confirmed robustly wrong-signed - higher
    # fcf_yield predicts LOWER forward returns in every window tested (robustly
    # wrong-signed). Stays fetched/computed/displayed (sec_valuations.fcf_yield), just
    # unconsumed here, same "computed but unscored" convention as ev_ebitda/ev_revenue.

    # Dividend yield: kept as a scored input on explicit user directive over the
    # statistically-stronger net_payout_yield alternative (t=3.05 vs t=1.55-2.28) -
    # net_payout_yield stays computed/stored but unconsumed. sec_valuations.dividend_yield
    # (migration 1146) is a decimal fraction (0.03 = 3%). Gate is `is not None`, not `> 0`:
    # 0.0 is a real, correctly-computed non-dividend-paying value (56% of universe), not
    # missing data - a `> 0` gate previously misrouted it away from the floor score.
    # Weight is intentionally modest (10%) since its own predictive evidence is weak and
    # inconsistent across sub-periods.
    if metrics.get("dividend_yield") is not None:
        div = min(metrics["dividend_yield"] * 100, 6)  # decimal -> percent, cap 6%
        div_score = min(100, div * 16.7)
        weighted_sum += div_score * 0.10
        total_weight += 0.10

    # Forward P/E was briefly removed, then re-added (see the scored block above) - kept
    # for institutional pedigree despite thin backtestable history.

    # EV/EBITDA and EV/Revenue REMOVED from scoring: ps_ratio/ev_revenue correlate r=1.00
    # and pe_ratio/ev_ebitda correlate r=0.93 (near-duplicates), pooled n=45,806. Both
    # fields stay fetched/displayed, just unscored, same convention as other
    # computed-but-unscored fields in this file. Freed weight went to PB/PS/FCF
    # yield/Dividend yield/Margin of Safety.

    # MARGIN OF SAFETY REMOVED FROM SCORING: not a duplicate signal (max |r|=0.21 with other
    # Value inputs) but a DCF-based per-stock screening tool rather than an objective
    # cross-sectional yield ratio like mainstream Value methodologies (MSCI/Russell/S&P/
    # Fama-French) use - and its own t-stat is unstable across sub-periods (0.30 to 2.12).
    # margin_of_safety_pct/intrinsic_value_per_share stay computed/stored as the Deep Value
    # page's primary metrics; freed weight went to PB/PS.

    # SIZE (market cap) retired entirely as a pillar/input (see BASE_PILLAR_WEIGHTS) -
    # size_proxy's strong coefficient was substantially an MNAR coverage artifact.
    # market_cap remains stored for display only.

    # AMIHUD ILLIQUIDITY - tested and found real/reproducible (t=2.99 full sample, positive
    # in both sub-period halves, not just a size proxy) but removed anyway: illiquidity is
    # its own distinct risk-factor family in the literature (Amihud 2002; Pastor-Stambaugh
    # 2003), conceptually separate from cheapness-vs-fundamentals, which is what this
    # pillar should measure. Stays computed/stored (technical_data_daily.amihud_illiquidity)
    # but unconsumed here.

    if total_weight > 0:
        return weighted_sum / total_weight
    logger.debug(f"[STOCK_SCORES] No value metrics found to score for {symbol}")
    logger.debug(f"[STOCK_SCORES] Returning data_unavailable marker for value_score({symbol}) - no scoreable fields")
    return {"symbol": symbol, "data_unavailable": True, "reason": "no_value_scores_computed"}
