"""Fetcher functions for market data, exposure factors, risk metrics, and sector data."""

import logging
import threading
from typing import Any, cast

from utils.safe_data_conversion import StrictValidationError, safe_float, safe_int

from .api_data_layer import api_call

logger = logging.getLogger(__name__)


def record_data_quality_issue(*args: object, **kwargs: object) -> None:
    """Placeholder for data quality issue recording."""


_markets_cache: dict[str, Any] = {}
_markets_lock = threading.Lock()


def _format_fetcher_error(fetcher_name: str, error: Exception) -> str:
    """Format fetcher error with endpoint context for better troubleshooting.

    Returns error string like: "Fetcher run (/api/algo/last-run: Last algo run status) timed out"
    """
    from .fetchers_common import FETCHER_METADATA

    meta = FETCHER_METADATA.get(fetcher_name)
    endpoint = meta.get("endpoint", "unknown endpoint") if meta else "unknown endpoint"
    desc = meta.get("desc", "") if meta else ""

    error_type = type(error).__name__
    error_msg = str(error)

    context = f"{endpoint}"
    if desc:
        context += f": {desc}"

    if error_msg:
        return f"Fetcher {fetcher_name} ({context}) - {error_type}: {error_msg}"
    else:
        return f"Fetcher {fetcher_name} ({context}) - {error_type}"


def _get_endpoint_path(fetcher_key: str, params: dict[str, Any] | None = None) -> str:
    """Map fetcher key to full endpoint path with optional query parameters.

    Examples:
      _get_endpoint_path('pos') → '/api/algo/positions'
      _get_endpoint_path('trades', params={'limit': 10}) → '/api/algo/trades' (params passed to api_call)
    """
    from .fetchers_common import FETCHER_METADATA

    meta = FETCHER_METADATA.get(fetcher_key)
    if not meta:
        # For endpoints with direct paths (like '/api/algo/last-run')
        return fetcher_key
    endpoint = meta.get("endpoint", "")
    if not endpoint:
        return fetcher_key
    return endpoint


def _get_markets_cached() -> dict[str, Any]:
    """Issue 14 FIX: Unified fetch for /api/algo/markets endpoint with 503 fallback.

    Both fetch_market and fetch_exp_factors need the same endpoint. This
    caches the result to avoid duplicate API calls when both are fetched
    in parallel. Thread-safe with lock to ensure single API call.

    On transient 503 errors: Attempts to use stale cache from previous successful calls
    to maintain dashboard stability during API service interruptions.
    """
    if "result" in _markets_cache:
        return cast(dict[str, Any], _markets_cache["result"])

    with _markets_lock:
        if "result" in _markets_cache:
            return cast(dict[str, Any], _markets_cache["result"])

        try:
            data = api_call("/api/algo/markets")

            # CRITICAL: Never fall back to stale market data. Market prices must be current.
            # If API is unavailable, it's better to fail and alert the user than to show
            # outdated prices that could lead to incorrect position sizing.
            if data.get("_is_transient_503"):
                error_result = {
                    "_error": "Market data API unavailable (503). Fresh market prices required for trading decisions."
                }
                logger.error("API /api/algo/markets returned 503 - returning error, not stale cache")
                # Don't cache 503 error - let next call retry the API
                return error_result

            # Only cache successful responses (no _error field)
            if not data.get("_error"):
                _markets_cache["result"] = data
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
            record_data_quality_issue("market", "api_call", "api_error", error_msg)
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
            # SPY close is in current object, not market_health
            spy_raw = current.get("spy_close")
            if spy_raw is None:
                spy_raw = mkt.get("spy_close")

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
            return FetcherValidator.build_error_response(error_msg)

        # Circuit breaker halt reasons - validate but allow graceful fallback to empty list
        halt_reasons_raw = current.get("halt_reasons")
        halt_reasons: list[Any] = []
        if halt_reasons_raw is None:
            # Halt reasons should be provided but if missing, default to empty list to allow dashboard display
            logger.warning(
                f"[MARKET DATA] Circuit breaker halt reasons missing from current.halt_reasons. "
                f"Defaulting to empty list. Current keys: {list(current.keys())}"
            )
            record_data_quality_issue("market", "data_quality", "missing_halt_reasons")
            halt_reasons = []
        elif not isinstance(halt_reasons_raw, list):
            # Halt reasons must be a list if provided
            logger.warning(
                f"[MARKET DATA] Circuit breaker halt reasons wrong type (got {type(halt_reasons_raw).__name__}). "
                f"Defaulting to empty list. Value: {halt_reasons_raw}"
            )
            record_data_quality_issue("market", "data_quality", "invalid_halt_reasons_type")
            halt_reasons = []
        else:
            halt_reasons = halt_reasons_raw

        return {
            "pct": safe_float(current.get("exposure_pct"), field_name="market.exposure_pct"),
            "tier": tier,
            "halts": halt_reasons,
            "vix": vix,
            "stage": market_health.get("market_stage"),
            "trend": market_health.get("market_trend"),
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
            "fed": market_health.get("fed_rate_environment"),
        }
    except Exception as e:
        error_msg = _format_fetcher_error("mkt", e)
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
            record_data_quality_issue("exp_factors", "api_call", "api_error", error_msg)
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
        return {
            "exposure_pct": safe_float(current.get("exposure_pct"), field_name="exposure.exposure_pct"),
            "raw_score": safe_float(current.get("raw_score"), field_name="exposure.raw_score"),
            "regime": current.get("regime"),
            "factors": current.get("factors"),
        }
    except Exception as e:
        error_msg = _format_fetcher_error("exp_factors", e)
        logger.error(error_msg)
        record_data_quality_issue("exp_factors", "exception", type(e).__name__, str(e))
        return FetcherValidator.build_error_response(error_msg)


def fetch_risk_metrics(c: None) -> dict[str, Any]:
    """API-only risk metrics. Fail-fast: error only on failure.

    Note: stressed_var_pct requires 365+ days of portfolio history; may be None
    during ramp-up. All other fields are required for meaningful risk display.
    """
    from dashboard.fetcher_validator import FetcherValidator

    try:
        data = api_call(_get_endpoint_path("risk"))

        # Check for API error
        is_error, error_msg = FetcherValidator.check_api_error(data)
        if is_error:
            record_data_quality_issue("risk", "api_call", "api_error", error_msg)
            return FetcherValidator.build_error_response(error_msg)

        d = data
        # stressed_var_pct is optional (requires 365+ days of history); others required
        required_fields = ["var_pct_95", "cvar_pct_95", "portfolio_beta", "top_5_concentration"]
        missing_fields = [f for f in required_fields if f not in d or d[f] is None]
        if missing_fields:
            error_msg = f"Risk metrics API response missing required fields: {missing_fields}"
            logger.error(error_msg)
            record_data_quality_issue("risk", "validation", "missing_required_fields", str(missing_fields))
            return FetcherValidator.build_error_response(error_msg)

        return {
            "date": d.get("report_date"),
            "var95": safe_float(d["var_pct_95"]),
            "cvar95": safe_float(d["cvar_pct_95"]),
            "svar": safe_float(d.get("stressed_var_pct"), default=None),
            "beta": safe_float(d["portfolio_beta"]),
            "conc5": safe_float(d["top_5_concentration"]),
        }
    except Exception as e:
        error_msg = _format_fetcher_error("risk", e)
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
            record_data_quality_issue("srank", "api_call", "api_error", error_msg)
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
        error_msg = _format_fetcher_error("srank", e)
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
            record_data_quality_issue("sec_rot", "api_call", "api_error", error_msg)
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
            error_msg = "Sector rotation data unavailable: 'items' array is empty. Cannot proceed without rotation signal."
            logger.error(error_msg)
            record_data_quality_issue("sec_rot", "validation", "empty_items_array")
            return FetcherValidator.build_error_response(error_msg)

        row = items[0]
        return {
            "date": row.get("date"),
            "signal": row.get("signal", ""),
            "strength": safe_float(row.get("spread"), default=None, field_name="sec_rot.spread"),
            "weeks": row.get("weeks_persistent", 1),
            "def_score": safe_float(
                row.get("defensive_lead_score"),
                default=None,
                field_name="sec_rot.defensive_lead_score",
            ),
            "cyc_score": safe_float(
                row.get("cyclical_weak_score"),
                default=None,
                field_name="sec_rot.cyclical_weak_score",
            ),
        }
    except Exception as e:
        error_msg = _format_fetcher_error("sec_rot", e)
        logger.error(error_msg)
        record_data_quality_issue("sec_rot", "exception", type(e).__name__, str(e))
        return FetcherValidator.build_error_response(error_msg)
