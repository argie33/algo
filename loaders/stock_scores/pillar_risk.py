"""Risk pillar: `_get_stability_metrics`/`_score_risk`, extracted verbatim (no logic change)
from loaders/load_stock_scores.py. StockScoresLoader keeps same-name, same-signature instance
methods that delegate here, passing RISK_MIN_WEIGHT_AVAILABLE/NEAR_ZERO_LIQUIDITY_THRESHOLD
through explicitly (those module constants stay defined in load_stock_scores.py - other
modules/tests import them directly from there, so they aren't moved here).
"""

import logging
from typing import Any

from loaders.stock_scores import scoring_curves
from utils.type_conversion import safe_float

logger = logging.getLogger(__name__)


def _get_stability_metrics(stability_cache: dict[str, tuple[Any, ...]], symbol: str) -> dict[str, Any]:
    """Fetch stability metrics for symbol.

    Returns explicit marker dict if data is unavailable (either no row or data_unavailable=True).
    Raises RuntimeError on database errors or data type mismatches.

    VALIDATION RULES:
    - Row length validation: Must have 9 columns (volatility_252d, volatility_60d,
      volatility_30d, beta, downside_volatility_252d/60d/30d, max_drawdown_1y,
      data_unavailable)
    - Schema mismatch (len(row) < 9) → raises ValueError immediately
    - All numeric fields converted via safe_float() (detects data corruption)
    - data_unavailable=True flag → returns marker dict even if row exists (not NULLs)
    - No row at all → returns marker dict with reason="no_stability_metrics_found"

    debt_to_assets/debt_to_equity/current_ratio/quick_ratio/cash_per_share/
    revenue_concentration_hhi are deliberately NOT merged in here - stability tracks
    price-volatility/risk-of-loss character, not balance-sheet fundamentals; those are
    scored under Quality instead (or, for revenue_concentration_hhi, not scored at all).
    """
    row = stability_cache.get(symbol)
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


def _score_risk(
    metrics: dict[str, Any] | None,
    symbol: str,
    risk_min_weight_available: float,
    near_zero_liquidity_threshold: float,
) -> float | dict[str, Any]:
    """Score risk metrics on 0-100 scale using price volatility / risk-of-loss signals only.

    Scores every stability-related field the frontend's Risk tab displays via a weighted
    blend. Volatility/beta/drawdown inputs are treated identically (not just down-weighted)
    when avg_dollar_volume_20d is known and below `near_zero_liquidity_threshold` - a
    frozen/near-frozen price series produces mechanically-suppressed (e.g. exactly 0.0)
    volatility that isn't a genuine low-risk signal.

    RETURN TYPES (STRICT):
    - available weight >= risk_min_weight_available → returns float (0-100)
    - metrics marked data_unavailable=True → returns marker dict (never None)
    - metrics is None or missing → returns marker dict (never None)
    - 0 < available weight < risk_min_weight_available → returns marker dict with
      reason="insufficient_risk_inputs_thin_sample" (added 2026-08-31 - see
      RISK_MIN_WEIGHT_AVAILABLE's own docstring, same thin-sample-extrapolation principle as
      Growth/Quality)
    - all risk fields None → returns marker dict with reason="no_risk_scores_computed"

    ERROR HANDLING:
    - Type conversion errors → RuntimeError (via _safe_float)
    - Negative volatility → treated as 0 (impossible case, but defensive)

    MINIMUM DATA REQUIREMENT: available weight (volatility_60d 0.45 + volatility_252d 0.15 +
    beta 0.15 + max_drawdown_1y 0.10 + avg_dollar_volume_20d/Liquidity 0.15, current as of
    the 2026-09-01 Liquidity reweight - see that field's own docstring below) must reach
    risk_min_weight_available - see RISK_MIN_WEIGHT_AVAILABLE's own docstring for why a single
    thin field (e.g. max_drawdown_1y alone) is no longer enough. If all stability metrics
    are None, returns data_unavailable marker.
    Critical metric for stock scoring (high priority upstream loader).
    """
    if not metrics or metrics.get("data_unavailable"):
        logger.warning(f"[STOCK_SCORES] Returning data_unavailable marker for risk_score({symbol})")
        return {"symbol": symbol, "data_unavailable": True, "reason": "no_risk_metrics_data"}

    weighted_sum = 0.0
    total_weight = 0.0

    # Weights: Volatility 60D 45% + Volatility 252D 15% + Beta 15% + Max Drawdown 1Y 10% +
    # Liquidity 15% (see docstring). Debt-to-Assets stays fetched via Quality's own
    # debt_to_assets read (quality_inputs on the scores API), not scored by this pillar.

    # NEAR_ZERO_LIQUIDITY_THRESHOLD gate (see that constant's own docstring): a near-zero
    # or frozen-price series makes volatility_60d/volatility_252d/beta measurement noise,
    # not a real signal - skip their weight here rather than trust a fabricated "calm"
    # reading. Only gates when avg_dollar_volume_20d is actually known; missing liquidity
    # data doesn't imply thin trading, so it leaves these inputs untouched.
    adv20 = metrics.get("avg_dollar_volume_20d")
    price_stats_unreliable = adv20 is not None and 0 <= adv20 < near_zero_liquidity_threshold

    if not price_stats_unreliable and metrics.get("volatility_60d") is not None:
        v60_score = scoring_curves._vol_curve_score(max(0, metrics["volatility_60d"]))
        weighted_sum += v60_score * 0.45
        total_weight += 0.45

    if not price_stats_unreliable and metrics.get("volatility_252d") is not None:
        v252_score = scoring_curves._vol_curve_score(max(0, metrics["volatility_252d"]))
        weighted_sum += v252_score * 0.15
        total_weight += 0.15

    # Beta: close to 1.0 is best, target 0.8-1.2 for market-correlated swing trading.
    # Deliberately not the literature's low-beta preference (Frazzini & Pedersen 2014
    # "Betting Against Beta") - this codebase consistently targets market-correlated
    # moves for swing-trading fit rather than minimum systematic risk, a repeated,
    # deliberate design choice, not an oversight.
    #
    # Beta is a signed regression coefficient, not a magnitude - must NOT be clipped to
    # max(0, beta) like the volatility/drawdown magnitude inputs above/below. Negative-beta
    # (inverse-correlated) names are real; |beta-1.0| naturally saturates via min(diff, 2.0).
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
        dd_score = scoring_curves._max_drawdown_curve_score(drawdown_pct)
        weighted_sum += dd_score * 0.10
        total_weight += 0.10

    # Liquidity (20-trading-day average dollar volume): scores thin-volume names low
    # because they're genuinely un-tradeable at this system's own min_adv_dollars floor,
    # even though academic literature (Amihud 2002) rewards illiquidity as a return
    # premium for buy-and-hold investors - that premium doesn't apply to this pillar's
    # swing-trading horizon, where thin volume is a pure execution cost (same non-alpha,
    # swing-trading-fit footing as Beta above, not a contradiction of Amihud).
    # Curve breakpoints anchor to algo_config.min_adv_dollars ($500K -> score 35, exactly
    # the Phase 7/8 trade-eligibility floor) rather than an invented threshold.
    if metrics.get("avg_dollar_volume_20d") is not None and metrics["avg_dollar_volume_20d"] > 0:
        liq_score = scoring_curves._liquidity_curve_score(metrics["avg_dollar_volume_20d"])
        weighted_sum += liq_score * 0.15
        total_weight += 0.15

    if total_weight >= risk_min_weight_available:
        return weighted_sum / total_weight
    if total_weight > 0:
        logger.info(
            f"[STOCK_SCORES] {symbol} risk_score withheld: only {total_weight:.2f}/1.00 weight "
            f"available, below RISK_MIN_WEIGHT_AVAILABLE={risk_min_weight_available}. See that "
            f"constant's docstring - a thin-weight renormalization is not an honest partial score."
        )
        return {
            "symbol": symbol,
            "data_unavailable": True,
            "reason": "insufficient_risk_inputs_thin_sample",
        }
    logger.debug(f"[STOCK_SCORES] Returning data_unavailable marker for risk_score({symbol}) - no scoreable fields")
    return {"symbol": symbol, "data_unavailable": True, "reason": "no_risk_scores_computed"}
