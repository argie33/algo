"""Fetcher functions for market data, exposure factors, risk metrics, and sector data."""

import logging
import threading
from typing import Any, cast

from utils.safe_data_conversion import StrictValidationError, safe_float, safe_int

from .api_data_layer import api_call
from .fetchers_common import format_fetcher_error, get_endpoint_path, record_data_quality_issue

logger = logging.getLogger(__name__)


_markets_cache: dict[str, Any] = {}
_markets_lock = threading.Lock()


def clear_markets_cache() -> None:
    """Clear the markets cache to ensure fresh data on next fetch.

    Called by load_all() to prevent stale data between refresh cycles.
    """
    with _markets_lock:
        _markets_cache.clear()


def _get_markets_cached() -> dict[str, Any]:
    """Unified fetch for /api/algo/markets endpoint (cached, no stale fallback).

    Both fetch_market and fetch_exp_factors need the same endpoint. This
    caches the result to avoid duplicate API calls when both are fetched
    in parallel. Thread-safe with lock to ensure single API call.

    CRITICAL: Never returns stale cache. Market prices must be current for accurate
    position sizing. Cache TTL is 60 seconds (within-cycle only). If API unavailable,
    returns error dict instead.
    """
    now = __import__("time").time()
    if "result" in _markets_cache and "_time" in _markets_cache and (now - _markets_cache["_time"]) < 60:
        return cast(dict[str, Any], _markets_cache["result"])

    with _markets_lock:
        if "result" in _markets_cache and "_time" in _markets_cache and (now - _markets_cache["_time"]) < 60:
            return cast(dict[str, Any], _markets_cache["result"])

        try:
            data = api_call("/api/algo/markets")

            # CRITICAL: Never fall back to stale market data. Market prices must be current.
            # If API is unavailable (503), return error — never return stale cache.
            # Stale prices could lead to incorrect position sizing and losses.
            # The 503 response indicates service degradation, so dashboard MUST show error state.
            if data.get("_error"):
                # API error — no caching, no fallback to stale data
                logger.error(f"API /api/algo/markets failed: {data.get('_error')}")
                return data

            # Only cache successful responses (no _error field) with timestamp
            _markets_cache["result"] = data
            _markets_cache["_time"] = now
            return data
        except Exception as e:
            error_result = {"_error": str(e)}
            # Don't cache errors - let next call retry
            return error_result


def fetch_market(c: None) -> dict[str, Any]:
    """Issue 3 FIX: API-only market data.

    STRICT MODE: SPY price and VIX are critical for position sizing. Missing them
    is a critical data freshness issue, not a fallback-to-None situation.

    If VIX is NULL, it means load_market_health_daily ran but yfinance returned
    no valid data (likely all values < 5.0 threshold). This is a data quality issue,
    not a missing loader issue.

    Issue 14 FIX: Uses cached markets endpoint to avoid duplicate API calls
    when fetch_exp_factors also needs the same data.
    """
    from dashboard.fetcher_validator import FetcherValidator

    try:
        mkt = _get_markets_cached()

        # Check for API error
        is_error, error_msg = FetcherValidator.check_api_error(mkt)
        if is_error:
            record_data_quality_issue("market", "api_call", "api_error", error_msg or "Unknown API error")
            return mkt

        # API response is unwrapped so data is at top level (statusCode + fields)
        current = mkt.get("current")
        market_health = mkt.get("market_health")
        if not isinstance(current, dict) or not isinstance(market_health, dict):
            error_msg = "Market API response missing 'current' or 'market_health' dict"
            logger.error(error_msg)
            record_data_quality_issue("market", "critical_field", "missing_current_or_health")
            return FetcherValidator.build_error_response(error_msg)

        # VIX and SPY are critical - fail if missing or invalid
        try:
            vix_raw = market_health.get("vix_level")
            spy_raw = current.get("spy_close")

            # Both SPY and VIX are REQUIRED for position sizing
            if vix_raw is None:
                error_msg = "Critical market data missing: VIX level required but not provided by API"
                logger.error(error_msg)
                record_data_quality_issue("market", "critical_field", "missing_vix")
                return FetcherValidator.build_error_response(error_msg)
            if spy_raw is None:
                error_msg = "Critical market data missing: SPY close required but not provided by API"
                logger.error(error_msg)
                record_data_quality_issue("market", "critical_field", "missing_spy")
                return FetcherValidator.build_error_response(error_msg)

            vix = float(vix_raw)
            spy = float(spy_raw)

            if vix <= 0:
                error_msg = (
                    f"Critical market data invalid: VIX = {vix} (must be > 0). Data quality issue in yfinance pipeline."
                )
                logger.error(error_msg)
                record_data_quality_issue("market", "critical_field", "invalid_vix", f"vix={vix}")
                return FetcherValidator.build_error_response(error_msg)
        except StrictValidationError as e:
            error_msg = f"Critical market data conversion failed: {e!s}"
            logger.error(error_msg)
            record_data_quality_issue("market", "critical_field", "conversion_failed", str(e))
            return FetcherValidator.build_error_response(error_msg)

        # Issue #9: Market regime is REQUIRED - no fallback to "unknown"
        tier = current.get("regime")
        if not tier:
            error_msg = (
                f"[MARKET CRITICAL] Market regime missing from current.regime. "
                f"Cannot position size without regime tier. "
                f"Current keys: {list(current.keys())}"
            )
            logger.error(error_msg)
            record_data_quality_issue("market", "critical_field", "missing_regime")
            # Raise instead of returning error dict for consistency with halt_reasons validation below
            raise ValueError(error_msg)

        # Explicit handling for optional fields with visibility flags
        market_stage = market_health.get("market_stage")
        stage_unavailable = market_stage is None
        if stage_unavailable:
            logger.debug("Optional market data missing: market_stage not provided by API")

        market_trend = market_health.get("market_trend")
        trend_unavailable = market_trend is None
        if trend_unavailable:
            logger.debug("Optional market data missing: market_trend not provided by API")

        fed_env = market_health.get("fed_rate_environment")
        fed_unavailable = fed_env is None
        if fed_unavailable:
            logger.debug("Optional market data missing: fed_rate_environment not provided by API")

        # CRITICAL: Circuit breaker halt reasons validation - fail fast on missing data
        halt_reasons_raw = current.get("halt_reasons")
        if halt_reasons_raw is None:
            raise ValueError(
                f"[MARKET DATA CRITICAL] Circuit breaker halt reasons missing from current data. "
                f"Halt validation is REQUIRED for trading safety. Cannot proceed without halt data. "
                f"Current keys: {list(current.keys())}"
            )
        if not isinstance(halt_reasons_raw, list):
            raise ValueError(
                f"[MARKET DATA CRITICAL] Circuit breaker halt reasons wrong type (got {type(halt_reasons_raw).__name__}). "
                f"Expected list[str]. Cannot proceed with invalid halt data. Value: {halt_reasons_raw}"
            )
        halt_reasons = halt_reasons_raw

        result = {
            "pct": safe_float(current.get("exposure_pct"), field_name="market.exposure_pct"),
            "tier": tier,
            "halts": halt_reasons,
            "vix": vix,
            "dist": safe_int(current.get("distribution_days"), field_name="market.distribution_days"),
            "spy": spy,
            "spy_chg": safe_float(market_health.get("spy_change_pct"), field_name="market.spy_change_pct"),
            "upvol": safe_float(
                market_health.get("up_volume_percent"),
                field_name="market.up_volume_percent",
            ),
            "adr": safe_float(
                market_health.get("advance_decline_ratio"),
                field_name="market.advance_decline_ratio",
            ),
            "nh": safe_int(
                market_health.get("new_highs_count"),
                field_name="market.new_highs_count",
            ),
            "nl": safe_int(market_health.get("new_lows_count"), field_name="market.new_lows_count"),
            "pcr": safe_float(market_health.get("put_call_ratio"), field_name="market.put_call_ratio"),
            "bmom": safe_float(
                market_health.get("breadth_momentum_10d"),
                field_name="market.breadth_momentum_10d",
            ),
            "ycs": safe_float(
                market_health.get("yield_curve_slope"),
                field_name="market.yield_curve_slope",
            ),
        }

        # Conditionally include optional fields only if available
        if not stage_unavailable:
            result["stage"] = market_stage
        else:
            result["stage_unavailable"] = True

        if not trend_unavailable:
            result["trend"] = market_trend
        else:
            result["trend_unavailable"] = True

        if not fed_unavailable:
            result["fed"] = fed_env
        else:
            result["fed_unavailable"] = True

        return result
    except Exception as e:
        error_msg = format_fetcher_error("mkt", e)
        logger.error(error_msg)
        record_data_quality_issue("market", "exception", type(e).__name__, str(e))
        return {"_error": error_msg}


def fetch_exp_factors(c: None) -> dict[str, Any]:
    """Fetch 12-factor market exposure data. Uses /api/algo/markets (public, already fetched).

    Extracts factors from data.current.factors which has the full 12-factor breakdown
    needed by the exposure panel.

    Issue 14 FIX: Uses cached markets endpoint to avoid duplicate API calls
    when fetch_market also needs the same data.
    """
    from dashboard.fetcher_validator import FetcherValidator

    try:
        data = _get_markets_cached()

        # Check for API error
        is_error, error_msg = FetcherValidator.check_api_error(data)
        if is_error:
            record_data_quality_issue("exp_factors", "api_call", "api_error", error_msg or "Unknown API error")
            return FetcherValidator.build_error_response(error_msg)

        # Response: {statusCode, data: {current: {exposure_pct, raw_score, regime, factors}, ...}}
        inner = data
        if not isinstance(inner, dict):
            error_msg = "Unexpected response format from markets endpoint"
            logger.error(error_msg)
            record_data_quality_issue("exp_factors", "validation", "invalid_response_type")
            return FetcherValidator.build_error_response(error_msg)

        if "current" not in inner:
            error_msg = "Missing 'current' field in markets response"
            logger.error(error_msg)
            record_data_quality_issue("exp_factors", "validation", "missing_current_field")
            return FetcherValidator.build_error_response(error_msg)

        current = inner["current"]

        # Explicit handling for optional fields with visibility flags
        regime = current.get("regime")
        regime_unavailable = regime is None
        if regime_unavailable:
            logger.debug("Optional exposure data missing: regime not provided by API")

        factors = current.get("factors")
        factors_unavailable = factors is None
        if factors is not None and not isinstance(factors, (list, dict)):
            error_msg = f"Exposure factors must be list or dict, got {type(factors).__name__}"
            logger.error(error_msg)
            record_data_quality_issue("exp_factors", "validation", "invalid_factors_type", str(type(factors).__name__))
            return FetcherValidator.build_error_response(error_msg)
        if factors_unavailable:
            logger.debug("Optional exposure data missing: factors not provided by API")

        result: dict[str, Any] = {
            "exposure_pct": safe_float(current.get("exposure_pct"), field_name="exposure.exposure_pct"),
            "raw_score": safe_float(current.get("raw_score"), field_name="exposure.raw_score"),
        }

        if not regime_unavailable:
            result["regime"] = regime
        else:
            result["regime_unavailable"] = True

        if not factors_unavailable:
            result["factors"] = factors
        else:
            result["factors_unavailable"] = True

        return result
    except Exception as e:
        error_msg = format_fetcher_error("exp_factors", e)
        logger.error(error_msg)
        record_data_quality_issue("exp_factors", "exception", type(e).__name__, str(e))
        return FetcherValidator.build_error_response(error_msg)


def fetch_risk_metrics(c: None) -> dict[str, Any]:
    """API-only risk metrics. Fail-fast: error only on API failure.

    All fields are optional and may be None during ramp-up or with insufficient data:
    - VaR/CVaR require 5+ portfolio snapshots
    - Stressed VaR requires 365+ days of history
    - Beta/Concentration require open positions
    """
    from dashboard.fetcher_validator import FetcherValidator

    try:
        data = api_call(get_endpoint_path("risk"))

        # Check for API error
        is_error, error_msg = FetcherValidator.check_api_error(data)
        if is_error:
            record_data_quality_issue("risk", "api_call", "api_error", error_msg or "Unknown API error")
            return FetcherValidator.build_error_response(error_msg)

        d = data
        # All risk fields are optional (may be None during ramp-up or insufficient data)
        # VaR/CVaR require 5+ snapshots, stressed_var requires 365+ days, beta/concentration require positions

        # Explicit handling for optional fields with visibility flags
        report_date = d.get("report_date")
        date_unavailable = report_date is None
        if date_unavailable:
            logger.debug("Optional risk data missing: report_date not provided by API")

        result = {
            "var95": safe_float(d.get("var_pct_95"), default=None),
            "cvar95": safe_float(d.get("cvar_pct_95"), default=None),
            "svar": safe_float(d.get("stressed_var_pct"), default=None),
            "beta": safe_float(d.get("portfolio_beta"), default=None),
            "conc5": safe_float(d.get("top_5_concentration"), default=None),
        }

        if not date_unavailable:
            result["date"] = report_date
        else:
            result["date_unavailable"] = True

        return result
    except Exception as e:
        error_msg = format_fetcher_error("risk", e)
        logger.error(error_msg)
        record_data_quality_issue("risk", "exception", type(e).__name__, str(e))
        return FetcherValidator.build_error_response(error_msg)


def fetch_sector_ranking(c: None) -> dict[str, Any]:
    """Fetch per-sector rankings from /api/sectors (fail-fast: error if unavailable)."""
    from dashboard.fetcher_validator import FetcherValidator

    try:
        data = api_call("/api/sectors")

        # Check for API error
        is_error, error_msg = FetcherValidator.check_api_error(data)
        if is_error:
            record_data_quality_issue("srank", "api_call", "api_error", error_msg or "Unknown API error")
            return FetcherValidator.build_error_response(error_msg)

        raw = data
        items = None
        if isinstance(raw, dict):
            items = raw.get("items")
            if not isinstance(items, list):
                error_msg = "Sector ranking API response: 'items' field is not a list"
                logger.error(error_msg)
                record_data_quality_issue("srank", "validation", "items_not_list")
                return FetcherValidator.build_error_response(error_msg)
        elif isinstance(raw, list):
            items = raw
        else:
            error_msg = f"Sector ranking API response: expected dict or list, got {type(raw).__name__}"
            logger.error(error_msg)
            record_data_quality_issue("srank", "validation", "invalid_response_type")
            return FetcherValidator.build_error_response(error_msg)

        if not items:
            error_msg = "No sector ranking data available"
            logger.error(error_msg)
            record_data_quality_issue("srank", "validation", "no_items")
            return FetcherValidator.build_error_response(error_msg)

        return {"items": items}
    except Exception as e:
        error_msg = format_fetcher_error("srank", e)
        logger.error(error_msg)
        record_data_quality_issue("srank", "exception", type(e).__name__, str(e))
        return FetcherValidator.build_error_response(error_msg)


def fetch_sector_rotation(c: None) -> dict[str, Any]:
    """Fetch sector rotation signal from API. Fail-fast: error only on failure."""
    from dashboard.fetcher_validator import FetcherValidator

    try:
        data = api_call("/api/algo/sector-rotation")

        # Check for API error
        is_error, error_msg = FetcherValidator.check_api_error(data)
        if is_error:
            record_data_quality_issue("sec_rot", "api_call", "api_error", error_msg or "Unknown API error")
            return FetcherValidator.build_error_response(error_msg)

        raw = data
        if not isinstance(raw, dict):
            error_msg = f"Sector rotation API response: expected dict, got {type(raw).__name__}"
            logger.error(error_msg)
            record_data_quality_issue("sec_rot", "validation", "invalid_response_type")
            return FetcherValidator.build_error_response(error_msg)

        items = raw.get("items")
        if items is not None and not isinstance(items, list):
            error_msg = f"Sector rotation 'items' field must be list, got {type(items).__name__}"
            logger.error(error_msg)
            record_data_quality_issue("sec_rot", "validation", "items_not_list")
            return FetcherValidator.build_error_response(error_msg)

        if not items:
            error_msg = (
                "Sector rotation data unavailable: 'items' array is empty. Cannot proceed without rotation signal."
            )
            logger.error(error_msg)
            record_data_quality_issue("sec_rot", "validation", "empty_items_array")
            return FetcherValidator.build_error_response(error_msg)

        row = items[0]
        if "signal" not in row or not row.get("signal"):
            raise ValueError(
                f"CRITICAL: Sector rotation signal missing required 'signal' field. "
                f"Cannot display sector rotation without signal data. Row: {row}"
            )
        weeks_raw = row.get("weeks_persistent")
        if weeks_raw is None:
            raise ValueError(
                "CRITICAL: Sector rotation weeks_persistent missing. "
                "Cannot determine signal persistence without weeks duration. "
                "Check sector rotation calculation."
            )

        # Explicit handling for optional fields with visibility flags
        rotation_date = row.get("date")
        date_unavailable = rotation_date is None
        if date_unavailable:
            logger.debug("Optional sector rotation data missing: date not provided by API")

        spread = row.get("spread")
        spread_unavailable = spread is None
        if spread_unavailable:
            logger.debug("Optional sector rotation data missing: spread not provided by API")

        def_score_raw = row.get("defensive_lead_score")
        def_score_unavailable = def_score_raw is None
        if def_score_unavailable:
            logger.debug("Optional sector rotation data missing: defensive_lead_score not provided by API")

        cyc_score_raw = row.get("cyclical_weak_score")
        cyc_score_unavailable = cyc_score_raw is None
        if cyc_score_unavailable:
            logger.debug("Optional sector rotation data missing: cyclical_weak_score not provided by API")

        result = {
            "signal": row["signal"],
            "weeks": int(weeks_raw),
        }

        if not date_unavailable:
            result["date"] = rotation_date
        else:
            result["date_unavailable"] = True

        if not spread_unavailable:
            result["strength"] = safe_float(spread, field_name="sec_rot.spread")
        else:
            result["strength_unavailable"] = True

        if not def_score_unavailable:
            result["def_score"] = safe_float(def_score_raw, field_name="sec_rot.defensive_lead_score")
        else:
            result["def_score_unavailable"] = True

        if not cyc_score_unavailable:
            result["cyc_score"] = safe_float(cyc_score_raw, field_name="sec_rot.cyclical_weak_score")
        else:
            result["cyc_score_unavailable"] = True

        return result
    except Exception as e:
        error_msg = format_fetcher_error("sec_rot", e)
        logger.error(error_msg)
        record_data_quality_issue("sec_rot", "exception", type(e).__name__, str(e))
        return FetcherValidator.build_error_response(error_msg)
