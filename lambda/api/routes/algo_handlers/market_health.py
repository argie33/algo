"""Market-health/normalization/circuit-breaker route handlers, extracted from
lambda/api/routes/algo_handlers/market.py (2026-09-05, file-size ratchet: that file is a
Tier-2 bloater flagged for decomposition). Bodies are verbatim, no logic changed - only moved
file. Imported back into market.py (re-exported) since lambda/api/routes/algo.py and several
tests reference these as market.py's own attributes.
"""

from __future__ import annotations

import json
import logging
import math
from typing import Any

import psycopg2
from psycopg2.extensions import cursor
from routes.utils import (
    check_data_freshness,
    db_route_handler,
    error_response,
    json_response,
    list_response,
    safe_dict_convert,
    safe_json_serialize,
    validate_api_response,
)

from utils.validation import format_decimal_string, get_optional_field

logger = logging.getLogger(__name__)


def _normalize_market_health(mh: dict[str, Any]) -> Any:
    """Validate and normalize market_health dict. Fails fast if critical fields missing or invalid.

    Critical fields (halt circuit breaker): vix_level, market_stage, market_trend
    CRITICAL: vix_level must be numeric > 0 (VIX is never negative or zero)
    """
    critical_fields = {"vix_level", "market_stage", "market_trend"}
    missing = critical_fields - {k for k in mh.keys() if mh[k] is not None}
    if missing:
        raise ValueError(f"Market health missing critical fields: {missing}")

    # Validate VIX level is > 0 (invalid data would be <= 0)
    vix_raw = mh.get("vix_level")
    try:
        vix_level = float(vix_raw) if vix_raw is not None else None
        if vix_level is not None and vix_level <= 0:
            raise ValueError(f"VIX level must be > 0, got {vix_level}")
    except (TypeError, ValueError) as e:
        raise ValueError(f"VIX level validation failed: {e} (got {type(vix_raw).__name__}: {vix_raw})") from e

    # Validate data_unavailable markers are present (fail-fast if missing)
    data_unavailable_markers = {
        "put_call_ratio_data_unavailable",
        "yield_curve_data_unavailable",
        "fed_rate_data_unavailable",
    }
    missing_markers = data_unavailable_markers - {k for k in mh.keys() if k in data_unavailable_markers}
    if missing_markers:
        logger.error(
            f"[MARKET HEALTH VALIDATION] CRITICAL: Missing data_unavailable markers: {missing_markers}. "
            f"Market health dict missing required fields for data availability tracking. "
            f"Check: market_health_daily table schema and loader that populates put_call_ratio_data_unavailable, "
            f"yield_curve_data_unavailable, fed_rate_data_unavailable. "
            f"Without these markers, API cannot accurately report data availability to clients."
        )
        raise ValueError(
            f"Market health missing required data_unavailable markers: {missing_markers}. "
            f"Cannot determine which optional fields are truly unavailable."
        )

    # Extract optional enrichment fields explicitly (fail if type is wrong, allow None if missing)
    market_trend = mh.get("market_trend")
    market_stage = mh.get("market_stage")
    up_volume_pct = get_optional_field(mh, "up_volume_percent")
    ad_ratio = get_optional_field(mh, "advance_decline_ratio")
    new_highs = get_optional_field(mh, "new_highs_count")
    new_lows = get_optional_field(mh, "new_lows_count")
    breadth_10d = get_optional_field(mh, "breadth_momentum_10d")
    put_call = get_optional_field(mh, "put_call_ratio")
    put_call_unavailable_reason = get_optional_field(mh, "put_call_ratio_unavailable_reason")
    yield_curve = get_optional_field(mh, "yield_curve_slope")
    yield_curve_unavailable_reason = get_optional_field(mh, "yield_curve_unavailable_reason")
    fed_rate_env = get_optional_field(mh, "fed_rate_environment")
    fed_rate_unavailable_reason = get_optional_field(mh, "fed_rate_unavailable_reason")
    spy_change = get_optional_field(mh, "spy_change_pct")

    return {
        "market_trend": market_trend,
        "market_stage": market_stage,
        "vix_level": vix_level,
        "up_volume_percent": up_volume_pct,
        "advance_decline_ratio": ad_ratio,
        "new_highs_count": new_highs,
        "new_lows_count": new_lows,
        "breadth_momentum_10d": breadth_10d,
        "put_call_ratio": put_call,
        "put_call_ratio_data_unavailable": mh["put_call_ratio_data_unavailable"],
        "put_call_ratio_unavailable_reason": put_call_unavailable_reason,
        "yield_curve_slope": yield_curve,
        "yield_curve_data_unavailable": mh["yield_curve_data_unavailable"],
        "yield_curve_unavailable_reason": yield_curve_unavailable_reason,
        "fed_rate_environment": fed_rate_env,
        "fed_rate_data_unavailable": mh["fed_rate_data_unavailable"],
        "fed_rate_unavailable_reason": fed_rate_unavailable_reason,
        "spy_change_pct": spy_change,
    }


def _normalize_exposure(exp: dict[str, Any]) -> Any:
    """Validate and normalize exposure dict. Fails fast if critical fields missing or invalid type.

    Critical fields (position sizing, trading halts): exposure_pct, regime
    CRITICAL: exposure_pct must be numeric 0-100, regime must be string (not "unknown" or "")
    """
    critical_fields = {"exposure_pct", "regime"}
    missing = critical_fields - {k for k in exp.keys() if exp[k] is not None}
    if missing:
        raise ValueError(f"Market exposure missing critical fields: {missing}")

    # Type and range validation for exposure_pct (AWS position sizing depends on this)
    exposure_pct_raw = exp.get("exposure_pct")
    if exposure_pct_raw is None:
        raise ValueError("exposure_pct is required but missing")
    try:
        exposure_pct = float(exposure_pct_raw)
        # BUG FOUND 2026-08-10 (NaN-comparison-guard class): `<0`/`>100` never catch NaN
        # (NaN comparisons are always False in Python) - this function's own docstring says
        # "AWS position sizing depends on this", so a NaN would have passed as "valid".
        if math.isnan(exposure_pct) or math.isinf(exposure_pct) or exposure_pct < 0 or exposure_pct > 100:
            raise ValueError(f"exposure_pct {exposure_pct} outside valid range [0,100]")
    except (TypeError, ValueError) as e:
        raise ValueError(
            f"exposure_pct type/range validation failed: {e} "
            f"(got {type(exposure_pct_raw).__name__}: {exposure_pct_raw})"
        ) from e

    # Validate regime is not "unknown" or empty string
    regime = exp.get("regime")
    if not regime or regime == "unknown" or regime == "":
        raise ValueError(
            f"Market exposure regime is invalid: '{regime}'. "
            f"Must be one of: confirmed_uptrend, uptrend_under_pressure, caution, correction"
        )
    if regime not in ("confirmed_uptrend", "uptrend_under_pressure", "caution", "correction"):
        raise ValueError(f"Market exposure regime '{regime}' not recognized")

    halt_reasons = get_optional_field(exp, "halt_reasons", default=[])
    return {
        "exposure_pct": exposure_pct,
        "regime": regime,
        "halt_reasons": halt_reasons if halt_reasons is not None else [],
        "distribution_days": exp.get("distribution_days"),
    }


@db_route_handler("get market")
@validate_api_response("mkt")
def _get_market(cur: cursor) -> Any:
    try:
        cur.execute("SET LOCAL statement_timeout = '8000ms'")

        # CRITICAL: Fetch market health; fail fast if unavailable
        # Include data_unavailable markers for optional enrichment fields so API can signal
        # which fields are truly unavailable vs. present in the response
        # Skip non-trading days (weekends/holidays) to get last valid trading day's data
        # Filter out NULL vix_level to skip incomplete records from non-trading days
        cur.execute("""
            SELECT market_trend, market_stage, vix_level,
                   up_volume_percent, advance_decline_ratio, new_highs_count,
                   new_lows_count, breadth_momentum_10d, put_call_ratio,
                   put_call_ratio_data_unavailable, put_call_ratio_unavailable_reason,
                   yield_curve_slope, yield_curve_data_unavailable, yield_curve_unavailable_reason,
                   fed_rate_environment, fed_rate_data_unavailable, fed_rate_unavailable_reason,
                   spy_change_pct
            FROM market_health_daily
            WHERE vix_level IS NOT NULL
            ORDER BY date DESC LIMIT 1
        """)
        mh = cur.fetchone()
        if not mh:
            return error_response(503, "data_unavailable", "Market health data unavailable")
        mh_raw = safe_json_serialize(safe_dict_convert(mh))
        market_health = _normalize_market_health(mh_raw)

        # CRITICAL: Fetch exposure data; fail fast if unavailable
        # Skip non-trading days (weekends/holidays) to get last valid trading day's data
        cur.execute("""
            SELECT exposure_pct, regime, halt_reasons, distribution_days
            FROM market_exposure_daily
            WHERE date <= CURRENT_DATE
            ORDER BY date DESC LIMIT 1
        """)
        exp = cur.fetchone()
        if not exp:
            return error_response(503, "data_unavailable", "Market exposure data unavailable")
        exp_raw = safe_json_serialize(safe_dict_convert(exp))
        exposure = _normalize_exposure(exp_raw)

        # Parse JSON strings from database (halt_reasons is stored as JSON text)
        if exposure["halt_reasons"]:
            try:
                exposure["halt_reasons"] = (
                    json.loads(exposure["halt_reasons"])
                    if isinstance(exposure["halt_reasons"], str)
                    else exposure["halt_reasons"]
                )
            except (json.JSONDecodeError, TypeError):
                exposure["halt_reasons"] = []

        # CRITICAL: Fetch SPY close price; fail fast if unavailable
        cur.execute("""
            SELECT close FROM price_daily
            WHERE symbol = 'SPY'
            ORDER BY date DESC LIMIT 1
        """)
        spy_row = cur.fetchone()
        if not spy_row:
            return error_response(503, "data_unavailable", "SPY price data unavailable")
        spy_row = safe_dict_convert(spy_row)
        if spy_row.get("close") is None:
            return error_response(503, "data_unavailable", "SPY price data unavailable")
        spy_close = float(spy_row["close"])

        # Handle optional/enrichment fields that may be None (breadth data, sentiment, macro indicators)
        uv_val = market_health.get("up_volume_percent")
        adr_val = market_health.get("advance_decline_ratio")
        nh_val = market_health.get("new_highs_count")
        nl_val = market_health.get("new_lows_count")
        pcr_val = market_health.get("put_call_ratio")
        bm_val = market_health.get("breadth_momentum_10d")
        ycs_val = market_health.get("yield_curve_slope")
        spy_chg_val = market_health.get("spy_change_pct")

        # When today's put/call ratio genuinely has no fresh value (common pre-market: SPY
        # options open interest is a lagging figure and often reads 0 before the session
        # gets going), surface the last day it WAS available instead of leaving the dashboard
        # with nothing to show at all. Same lookback pattern already used for the same column
        # in algo/risk/market_factor_calculator.py - only ever reads a row explicitly NOT
        # flagged unavailable, so a failed-fetch value that was never cleared from the column
        # can't leak through as if it were real (that's the specific bug this pattern guards
        # against, per the comment on put_call_ratio_data_unavailable below). Does not change
        # put_call_ratio/put_call_ratio_data_unavailable themselves - those keep truthfully
        # reporting "no fresh value today" so any consumer trusting that flag is unaffected.
        pcr_stale_val = None
        pcr_stale_date = None
        if pcr_val is None:
            cur.execute("""
                SELECT date, put_call_ratio FROM market_health_daily
                WHERE put_call_ratio IS NOT NULL AND put_call_ratio_data_unavailable IS NOT TRUE
                ORDER BY date DESC LIMIT 1
            """)
            stale_row = cur.fetchone()
            if stale_row:
                stale_row = safe_dict_convert(stale_row)
                pcr_stale_val = stale_row.get("put_call_ratio")
                pcr_stale_date = stale_row.get("date")

        # Convert to appropriate types, allowing None for optional/enrichment fields
        # Include data_unavailable markers so frontend knows which fields are truly unavailable
        data = {
            "exposure_pct": float(exposure["exposure_pct"]),
            "regime": exposure["regime"],
            "halt_reasons": exposure["halt_reasons"],
            "vix_level": float(market_health["vix_level"]),
            "market_stage": int(market_health["market_stage"]),
            "market_trend": market_health["market_trend"],
            "distribution_days_4w": int(exposure["distribution_days"]),
            "spy_close": spy_close,
            "spy_change_pct": float(spy_chg_val) if spy_chg_val is not None else None,
            "up_volume_percent": float(uv_val) if uv_val is not None else None,
            "advance_decline_ratio": float(adr_val) if adr_val is not None else None,
            "new_highs_count": int(nh_val) if nh_val is not None else None,
            "new_lows_count": int(nl_val) if nl_val is not None else None,
            "put_call_ratio": float(pcr_val) if pcr_val is not None else None,
            # Trust the loader's own put_call_ratio_data_unavailable column (already normalized
            # above by _normalize_market_health) instead of re-deriving from NULL-ness - the two
            # can diverge, and the same re-derive-from-NULL anti-pattern already caused a real
            # stale-value bug elsewhere in this codebase (see algo/risk/market_factor_calculator.py).
            "put_call_ratio_data_unavailable": market_health["put_call_ratio_data_unavailable"],
            "put_call_ratio_stale_value": float(pcr_stale_val) if pcr_stale_val is not None else None,
            "put_call_ratio_stale_date": str(pcr_stale_date) if pcr_stale_date is not None else None,
            "put_call_ratio_unavailable_reason": (
                market_health.get("put_call_ratio_unavailable_reason")
                if market_health["put_call_ratio_data_unavailable"]
                else None
            ),
            "breadth_momentum_10d": float(bm_val) if bm_val is not None else None,
            "yield_curve_slope": float(ycs_val) if ycs_val is not None else None,
            "yield_curve_data_unavailable": market_health["yield_curve_data_unavailable"],
            "yield_curve_unavailable_reason": (
                market_health.get("yield_curve_unavailable_reason")
                if market_health["yield_curve_data_unavailable"]
                else None
            ),
            "fed_rate_environment": market_health.get("fed_rate_environment"),
            # CRITICAL FIX: Explicitly check if fed_rate_data_unavailable is True (not False default).
            # Do NOT silently default to False if field is missing - that masks data quality issues.
            # Consistency: Put_call_ratio and yield_curve use explicit None checks, apply same pattern here.
            "fed_rate_data_unavailable": market_health.get("fed_rate_data_unavailable"),
            "fed_rate_unavailable_reason": (
                market_health.get("fed_rate_unavailable_reason")
                if market_health.get("fed_rate_data_unavailable")
                else None
            ),
        }

        # BUG FOUND 2026-08-17: this endpoint never computed a real freshness signal for
        # market_health_daily/market_exposure_daily - the dashboard's MARKET panel
        # (dashboard/panels/market.py) instead self-computed "age" from the fetch's own
        # datetime.now(ET) timestamp, which is always ~0 seconds old regardless of how stale
        # the underlying VIX/exposure data actually is. VIX and market regime directly feed
        # position sizing (see this function's own "CRITICAL: fail fast if unavailable"
        # comments above) - stale data here with zero warning is a real risk. Mirrors the
        # already-correct pattern used for algo_positions/algo_trades/algo_signals freshness.
        freshness = check_data_freshness(cur, "market_health_daily", "date", warning_days=1)

        return json_response(200, data, data_freshness=freshness)
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        logger.error(
            f"Failed to fetch market: {type(e).__name__}: {e}\n  Operation: Query market_health_daily with date filter\n  Endpoint: GET /api/algo/market"
        )
        return error_response(503, "service_unavailable", "Failed to fetch market data")


@db_route_handler("get market factors")
def _get_market_factors(cur: cursor) -> Any:
    logger.debug("[MARKET_FACTORS] Function called - no validation decorator")
    try:
        cur.execute("SET LOCAL statement_timeout = '8000ms'")

        # Fetch exposure factors from market_exposure_daily
        cur.execute("""
            SELECT exposure_pct, raw_score, regime, factors
            FROM market_exposure_daily
            ORDER BY date DESC LIMIT 1
        """)
        row = cur.fetchone()

        if not row:
            return error_response(503, "data_unavailable", "Market exposure factors data not yet available")

        data_dict = safe_json_serialize(safe_dict_convert(row))

        # Parse factors if it's a JSON string
        factors = {}
        if data_dict.get("factors"):
            try:
                factors_val = data_dict.get("factors")
                if isinstance(factors_val, str):
                    factors = json.loads(factors_val)
                else:
                    factors = factors_val if isinstance(factors_val, dict) else {}
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"[MARKET_FACTORS] Failed to parse factors: {e}")
                factors = {}

        data = {
            "exposure_pct": format_decimal_string(data_dict.get("exposure_pct"), precision=2, allow_none=True),
            "raw_score": format_decimal_string(data_dict.get("raw_score"), precision=2, allow_none=True),
            "regime": data_dict.get("regime"),
            "factors": factors,
        }

        return json_response(200, data)
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        logger.error(
            f"Failed to fetch market factors: {type(e).__name__}: {e}\n  Operation: Calculate market exposure factors\n  Endpoint: GET /api/algo/market-factors"
        )
        return error_response(503, "service_unavailable", "Failed to fetch market factors")


@db_route_handler("get market sentiment")
@validate_api_response("mkt")
def _get_market_sentiment(cur: cursor) -> Any:
    # market_sentiment view provides: date, fear_greed_index, label, put_call_ratio, vix, sentiment_score.
    # bullish/bearish/neutral breakdown is not available in this view (AAII survey data lives in
    # aaii_sentiment instead) - only sentiment_score is used below.
    cur.execute("""
        SELECT sentiment_score, date
        FROM market_sentiment
        ORDER BY date DESC
        LIMIT 1
    """)
    row = cur.fetchone()

    if not row:
        return error_response(503, "no_data", "Market sentiment data not yet available")

    row = safe_dict_convert(row)

    if row.get("sentiment_score") is None:
        return error_response(503, "incomplete_data", "Market sentiment data incomplete")

    sentiment_score = float(row["sentiment_score"])
    bullish = None  # Not available in market_sentiment view
    bearish = None  # Not available in market_sentiment view
    neutral = None  # Not available in market_sentiment view

    trend = None
    if sentiment_score is not None:
        if sentiment_score > 60:
            trend = "BULLISH"
        elif sentiment_score > 40:
            trend = "NEUTRAL"
        else:
            trend = "BEARISH"

    return json_response(
        200,
        {
            # sentiment_score is validated non-None above; an extreme-bearish reading of
            # exactly 0 must not be hidden as "unavailable" by a falsy check.
            "sentiment": round(sentiment_score, 2),
            "trend": trend,
            "bullish_pct": round(bullish, 1) if bullish else None,
            "bearish_pct": round(bearish, 1) if bearish else None,
            "neutral_pct": round(neutral, 1) if neutral else None,
        },
    )


@db_route_handler("get trend criteria")
@validate_api_response("mkt")
def _get_trend_criteria(cur: cursor) -> Any:
    cur.execute("""
        SELECT
            COUNT(*) as total_symbols,
            COUNT(*) FILTER (WHERE price_above_sma50 = true) as above_sma50,
            COUNT(*) FILTER (WHERE sma50_above_sma200 = true) as sma50_above_sma200,
            COUNT(*) FILTER (WHERE price_above_sma200 = true) as above_sma200,
            COUNT(*) FILTER (WHERE weinstein_stage = 2) as stage2
        FROM trend_template_data
        WHERE date = (SELECT MAX(date) FROM trend_template_data)
    """)
    row = cur.fetchone()
    if not row:
        return error_response(503, "no_data", "Trend template data not yet available")
    row = safe_dict_convert(row)
    if "total_symbols" not in row or row["total_symbols"] is None:
        return error_response(503, "no_data", "Trend template data not yet available")
    total_symbols_val = row["total_symbols"]
    if int(total_symbols_val) == 0:
        return error_response(503, "no_data", "Trend template data not yet available")

    total_symbols = int(row["total_symbols"])
    criteria = [
        {
            "name": "Price Above 50-Day MA",
            "passing": int(row["above_sma50"]),
            "total": total_symbols,
        },
        {
            "name": "50-Day Above 200-Day MA",
            "passing": int(row["sma50_above_sma200"]),
            "total": total_symbols,
        },
        {
            "name": "Price Above 200-Day MA",
            "passing": int(row["above_sma200"]),
            "total": total_symbols,
        },
        {
            "name": "Stage 2 Uptrend (Weinstein)",
            "passing": int(row["stage2"]),
            "total": total_symbols,
        },
    ]

    return list_response(criteria, total=total_symbols, limit=None, offset=None)


def _is_any_circuit_breaker_triggered(
    metrics: dict[str, Any],
    drawdown_threshold: float,
    daily_loss_threshold: float,
    weekly_loss_threshold: float,
    open_risk_threshold: float,
    vix_threshold: float,
) -> bool:
    """Check if any circuit breaker metric exceeds its configured threshold.

    Args:
        metrics: Dict with keys portfolio_drawdown_pct, daily_loss_pct, weekly_loss_pct,
                open_risk_pct, vix_level
        *_threshold: Configured thresholds from algo_config (absolute values for comparisons)

    Returns:
        True if any metric >= threshold, False if all below thresholds or None.
    """
    if metrics.get("portfolio_drawdown_pct") is not None:
        if float(metrics["portfolio_drawdown_pct"]) >= drawdown_threshold:
            return True
    if metrics.get("daily_loss_pct") is not None:
        if float(metrics["daily_loss_pct"]) >= daily_loss_threshold:
            return True
    if metrics.get("weekly_loss_pct") is not None:
        if float(metrics["weekly_loss_pct"]) >= weekly_loss_threshold:
            return True
    if metrics.get("open_risk_pct") is not None:
        if float(metrics["open_risk_pct"]) >= open_risk_threshold:
            return True
    if metrics.get("vix_level") is not None:
        if float(metrics["vix_level"]) >= vix_threshold:
            return True
    return False


def _collect_phase2_circuit_breakers(cur: cursor, execution_health: dict[str, Any]) -> None:
    """Collect Phase 2 circuit breaker status with thresholds from algo_config.

    CRITICAL: Thresholds MUST come from algo_config (same source the real circuit breaker
    reads), not hardcoded. Dashboard indicator and real halt logic must stay in sync.
    If any threshold key is missing from algo_config, sets execution_health to None
    (unknown status), not a silent "all clear" with a guessed default.
    """
    cur.execute(
        """
        SELECT key, value FROM algo_config
        WHERE key IN ('halt_drawdown_pct', 'max_daily_loss_pct', 'max_weekly_loss_pct',
                      'max_total_risk_pct', 'vix_max_threshold')
        """
    )
    cb_config = {row[0]: row[1] for row in cur.fetchall()}
    required_keys = (
        "halt_drawdown_pct",
        "max_daily_loss_pct",
        "max_weekly_loss_pct",
        "max_total_risk_pct",
        "vix_max_threshold",
    )
    missing_keys = [k for k in required_keys if k not in cb_config]
    if missing_keys:
        logger.warning(f"[HEALTH] Phase 2 algo_config missing keys: {missing_keys}")
        execution_health["phase_2_circuit_breakers"] = None
        return

    drawdown_threshold = abs(float(cb_config["halt_drawdown_pct"]))
    daily_loss_threshold = float(cb_config["max_daily_loss_pct"])
    weekly_loss_threshold = float(cb_config["max_weekly_loss_pct"])
    open_risk_threshold = float(cb_config["max_total_risk_pct"])
    vix_threshold = float(cb_config["vix_max_threshold"])

    cur.execute(
        """
        SELECT portfolio_drawdown_pct, daily_loss_pct, weekly_loss_pct, open_risk_pct,
               vix_level, market_stage, check_date
        FROM circuit_breaker_status
        ORDER BY check_date DESC LIMIT 1
        """
    )
    cb_row = cur.fetchone()
    if cb_row:
        cb_dict = safe_dict_convert(cb_row)
        any_triggered = _is_any_circuit_breaker_triggered(
            cb_dict,
            drawdown_threshold=drawdown_threshold,
            daily_loss_threshold=daily_loss_threshold,
            weekly_loss_threshold=weekly_loss_threshold,
            open_risk_threshold=open_risk_threshold,
            vix_threshold=vix_threshold,
        )

        check_date = cb_dict.get("check_date")
        check_date_str = check_date.isoformat() if check_date and hasattr(check_date, "isoformat") else str(check_date)

        execution_health["phase_2_circuit_breakers"] = {
            "any_triggered": any_triggered,
            "drawdown_pct": (
                float(cb_dict["portfolio_drawdown_pct"]) if cb_dict.get("portfolio_drawdown_pct") is not None else None
            ),
            "daily_loss_pct": (float(cb_dict["daily_loss_pct"]) if cb_dict.get("daily_loss_pct") is not None else None),
            "weekly_loss_pct": (
                float(cb_dict["weekly_loss_pct"]) if cb_dict.get("weekly_loss_pct") is not None else None
            ),
            "open_risk_pct": (float(cb_dict["open_risk_pct"]) if cb_dict.get("open_risk_pct") is not None else None),
            "vix_level": float(cb_dict["vix_level"]) if cb_dict.get("vix_level") is not None else None,
            "last_check": check_date_str,
        }
    else:
        execution_health["phase_2_circuit_breakers"] = None
