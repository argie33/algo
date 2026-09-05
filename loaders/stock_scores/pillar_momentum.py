"""Momentum pillar: `_get_momentum_metrics`/`_score_momentum`, extracted verbatim (no logic
change) from loaders/load_stock_scores.py. StockScoresLoader keeps same-name, same-signature
instance methods that delegate here.
"""

import logging
import math
from typing import Any

import psycopg2

from loaders.stock_scores import scoring_curves
from utils.type_conversion import safe_float

logger = logging.getLogger(__name__)


def _get_momentum_metrics(
    momentum_cache: dict[str, tuple[Any, ...]],
    technical_cache: dict[str, tuple[Any, ...]],
    symbol: str,
) -> dict[str, Any]:
    """Fetch momentum/RS metrics for symbol from momentum_metrics table.

    Reads precomputed momentum values from momentum_metrics (populated by
    load_risk_metrics_daily.py):
    - momentum_1m, momentum_3m, momentum_6m, momentum_12m (already calculated)
    - data_unavailable flag (True if loader failed)

    Also merges in the latest RSI(14)/MACD/SMA-positioning from technical_data_daily (via
    `technical_cache`). These are a separate, independently-available source, so a symbol
    without usable price-return momentum can still contribute an RSI/MACD/SMA-only
    momentum score, and vice versa - "no momentum_metrics row at all" and "row present but
    data_unavailable=True" are treated identically (both mean no price-return momentum),
    since RSI/MACD/SMA carry their own dedicated weight slots in _score_momentum rather than
    substituting as a proxy for price-return momentum.

    Returns dict with momentum values (which may be None for individual timeframes if
    upstream loader failed to calculate them).
    """
    try:
        tech_row = technical_cache.get(symbol, None)
        rsi_14 = safe_float(tech_row[0], f"{symbol}.rsi_14", allow_none=True) if tech_row else None
        macd = safe_float(tech_row[1], f"{symbol}.macd", allow_none=True) if tech_row else None
        sma_50 = safe_float(tech_row[2], f"{symbol}.sma_50", allow_none=True) if tech_row else None
        sma_200 = safe_float(tech_row[3], f"{symbol}.sma_200", allow_none=True) if tech_row else None
        close = safe_float(tech_row[4], f"{symbol}.close", allow_none=True) if tech_row else None
        # Decimal fraction (0.05 = +5%), matching _score_momentum's ±10%-range-maps-to-0-100
        # formula - NOT the *100 percentage scale the scores API computes for display.
        price_vs_sma_50 = (close - sma_50) / sma_50 if close is not None and sma_50 else None
        price_vs_sma_200 = (close - sma_200) / sma_200 if close is not None and sma_200 else None

        row = momentum_cache.get(symbol, None)

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


def _score_momentum(metrics: dict[str, Any] | None, symbol: str) -> float | dict[str, Any]:
    """Score momentum metrics on 0-100 scale. Returns marker dict if no real data.

    Uses weighted scoring: Momentum 3m (20%) + 12-1 skip-month momentum (35%) + RSI(14)/
    MACD-sign technical-trend confirmation (37% combined, averaged) + SMA positioning (8%).
    Normalizes by total weight of available components so partial data doesn't deflate the
    score.

    RSI(14) and MACD-sign are averaged into one slot rather than weighted independently -
    they're highly correlated (r=0.58-0.70) and their multivariate regression coefficients
    flip sign against each other when weighted separately, the same redundancy treatment
    applied to Stability's volatility windows and this pillar's SMA(50)/SMA(200) pair.

    momentum_1m and the ROC composite (roc_20d/60d/120d/252d) are intentionally not scored
    standalone: ROC is the same return computation as the momentum windows over
    near-identical periods (pure duplication), and momentum_1m is excluded per the standard
    academic 12-1 momentum construction (Jegadeesh 1990) - most-recent-month return shows
    short-term reversal in low-momentum names but continuation in high-momentum names, an
    interaction a flat weighted score can't encode, so it's dropped rather than mis-scored.
    momentum_1m is still read below solely as an input to the mom_12_1 derivation.

    momentum_6m/momentum_12m are replaced by a derived 12-1 skip-month construction
    (mom_12_1, weight 35% = their prior combined 20%+15%) rather than stored as separate
    fields: momentum_6m was the most redundant of the three windows (correlated with both
    3m and 12m neighbors) and raw momentum_12m carries the same recency-contamination
    Jegadeesh 1990 excludes. mom_12_1 is algebraically derived here from momentum_12m and
    momentum_1m: ((1+momentum_12m/100)/(1+momentum_1m/100) - 1)*100.

    RSI's "higher RSI = more bullish" (trend-following) treatment is deliberately NOT
    flipped to the oscillator/mean-reversion convention despite an internal panel finding
    weak negative predictive correlation - the effect is a technical-analysis heuristic
    (no academic asset-pricing literature backing) that has decayed toward zero in the most
    recent ~3.5 years of data, so it's not acted on.

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
            score = scoring_curves._pct_to_score(metrics[key])
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
                mom_12_1_score = scoring_curves._pct_to_score(mom_12_1)
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
    # Use "macd" directly - technical_data_daily has no macd_line column (a same-named
    # column exists only on the unrelated momentum_metrics table), so a prior
    # macd_line-preferring lookup was silently always None.
    tech_trend_scores = []
    if metrics.get("rsi_14") is not None:
        tech_trend_scores.append(scoring_curves._rsi_to_score(metrics["rsi_14"]))
    macd = metrics.get("macd")
    if macd is not None:
        tech_trend_scores.append(70.0 if macd > 0 else 30.0 if macd < 0 else 50.0)
    if tech_trend_scores:
        weighted_sum += (sum(tech_trend_scores) / len(tech_trend_scores)) * 0.37
        total_weight += 0.37

    # ROC composite (roc_20d/60d/120d/252d) intentionally not scored - same
    # close.pct_change() computation as momentum_1m/3m/6m/12m over near-identical windows,
    # not a diversifying signal.

    # Price vs Moving Averages: premium over SMAs indicates uptrend
    sma_scores = []
    for sma_field in ["price_vs_sma_50", "price_vs_sma_200"]:
        sma_val = metrics.get(sma_field)
        if sma_val is not None:
            # Price above SMA = bullish, saturating at ±20%: +20% above = 100, -20% below = 0.
            sma_score = 50 + (sma_val / 0.2) * 50  # ±20% range maps to 0-100
            sma_scores.append(min(100, max(0, sma_score)))
    if sma_scores:
        weighted_sum += (sum(sma_scores) / len(sma_scores)) * 0.08
        total_weight += 0.08

    if total_weight > 0:
        return weighted_sum / total_weight
    logger.debug(f"[STOCK_SCORES] Returning data_unavailable marker for momentum_score({symbol}) - no scoreable fields")
    return {"symbol": symbol, "data_unavailable": True, "reason": "no_momentum_scores_computed"}
