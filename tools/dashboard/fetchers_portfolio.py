"""Fetcher functions for portfolio, positions, trades, and performance data."""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from .api_data_layer import api_call
from .panels.data_extractors import safe_get_dict, safe_get_list

ET = ZoneInfo("America/New_York")
logger = logging.getLogger(__name__)


def record_data_quality_issue(*args, **kwargs):
    """Placeholder for data quality issue recording."""


def _format_fetcher_error(fetcher_name: str, error: Exception) -> str:
    """Format fetcher error with endpoint context for better troubleshooting.

    Returns error string like: "Fetcher run (/api/algo/last-run: Last algo run status) timed out"
    """
    from .fetchers import FETCHER_METADATA

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


def _get_endpoint_path(fetcher_key: str, params: dict | None = None) -> str:
    """Map fetcher key to full endpoint path with optional query parameters.

    Examples:
      _get_endpoint_path('pos') → '/api/algo/positions'
      _get_endpoint_path('trades', params={'limit': 10}) → '/api/algo/trades' (params passed to api_call)
    """
    from .fetchers import FETCHER_METADATA

    meta = FETCHER_METADATA.get(fetcher_key)
    if not meta:
        # For endpoints with direct paths (like '/api/algo/last-run')
        return fetcher_key
    endpoint = meta.get("endpoint", "")
    if not endpoint:
        return fetcher_key
    return endpoint


def fetch_portfolio(c):
    """Fetch portfolio snapshot from API. Fails clean if unavailable.

    STRICT MODE: Uses direct conversion for critical financial fields (no defaults to 0).
    Missing data triggers error, not silent 0 values which are catastrophically misleading.
    """
    from tools.dashboard.fetcher_validator import FetcherValidator

    try:
        data = api_call("/api/algo/portfolio")
        port = data

        # Comprehensive validation using FetcherValidator
        required_fields = [
            "total_portfolio_value",
            "total_cash",
            "position_count",
            "last_run",
        ]
        valid, error_msg = FetcherValidator.validate_response(
            response=port,
            required_fields=required_fields,
            source_name="fetch_portfolio",
            max_age_seconds=432000,
            timestamp_field="last_run",
        )
        if not valid:
            logger.error(error_msg)
            for field in required_fields:
                if field not in port or port[field] is None:
                    record_data_quality_issue("portfolio", field, "missing_required_field")
            return FetcherValidator.build_error_response(error_msg)

        # Data is already validated at boundary; direct conversion
        tpv = float(port["total_portfolio_value"])
        tc = float(port["total_cash"])
        pc = int(port["position_count"])

        unrealized_pnl_dict = safe_get_dict(port.get("unrealized_pnl"))
        unrealized_pnl_pct = None
        if unrealized_pnl_dict and "total_pct" in unrealized_pnl_dict:
            val = unrealized_pnl_dict.get("total_pct")
            unrealized_pnl_pct = float(val) if val is not None else None

        return {
            "snapshot_date": port.get("last_run"),
            "total_portfolio_value": tpv,
            "total_cash": tc,
            "position_count": pc,
            "daily_return_pct": port.get("daily_return_pct"),
            "unrealized_pnl_pct": unrealized_pnl_pct,
            "cumulative_return_pct": port.get("cumulative_return_pct"),
            "max_drawdown_pct": port.get("max_drawdown_pct"),
            "largest_position_pct": port.get("largest_position_pct"),
            "data_age_seconds": port.get("data_age_seconds"),
        }
    except Exception as e:
        error_msg = _format_fetcher_error("port", e)
        logger.error(error_msg)
        record_data_quality_issue("portfolio", "exception", type(e).__name__, str(e))
        return {"_error": error_msg}


def fetch_positions(c):
    """Fetch positions via AWS API only (fail-fast: error if unavailable)."""
    from tools.dashboard.fetcher_validator import FetcherValidator

    try:
        data = api_call(_get_endpoint_path("pos"))

        # Check for API error
        is_error, error_msg = FetcherValidator.check_api_error(data)
        if is_error:
            record_data_quality_issue("pos", "api_call", "api_error", error_msg)
            return FetcherValidator.build_error_response(error_msg)

        result = data
        if isinstance(result, dict):
            items = result.get("items")
            if not isinstance(items, list):
                error_msg = "Positions API response: 'items' field is not a list"
                logger.error(error_msg)
                record_data_quality_issue("pos", "validation", "items_not_list")
                return FetcherValidator.build_error_response(error_msg)
        elif isinstance(result, list):
            items = result
        else:
            error_msg = "Positions API response: expected dict or list"
            logger.error(error_msg)
            record_data_quality_issue("pos", "validation", "invalid_response_type")
            return FetcherValidator.build_error_response(error_msg)
        return {"items": items, "timestamp": datetime.now(ET)}
    except Exception as e:
        error_msg = _format_fetcher_error("pos", e)
        logger.error(error_msg)
        record_data_quality_issue("pos", "exception", type(e).__name__, str(e))
        return FetcherValidator.build_error_response(error_msg)


def fetch_recent_trades(c):
    """AWS-only trades data. Fail-fast: error only on failure.

    Returns closed trades only - open positions are in the positions panel.
    Note: 503 means no closed trades yet (algo just started) - treat as no data.
    """
    from tools.dashboard.fetcher_validator import FetcherValidator

    try:
        data = api_call(
            _get_endpoint_path("trades"),
            params={"limit": 30, "status": "closed"},
        )

        # Check for API error - fail-fast: return error for all API failures
        is_error, error_msg = FetcherValidator.check_api_error(data)
        if is_error:
            record_data_quality_issue("trades", "api_call", "api_error", error_msg)
            return FetcherValidator.build_error_response(error_msg)

        result = data
        if isinstance(result, dict):
            trades = result.get("items")
            if not isinstance(trades, list):
                error_msg = "Trades API response: 'items' field is not a list"
                logger.error(error_msg)
                record_data_quality_issue("trades", "validation", "items_not_list")
                return FetcherValidator.build_error_response(error_msg)
        elif isinstance(result, list):
            trades = result
        else:
            error_msg = "Trades API response: expected dict or list"
            logger.error(error_msg)
            record_data_quality_issue("trades", "validation", "invalid_response_type")
            return FetcherValidator.build_error_response(error_msg)
        return {"items": trades, "timestamp": datetime.now(ET)}
    except Exception as e:
        error_msg = _format_fetcher_error("trades", e)
        logger.error(error_msg)
        record_data_quality_issue("trades", "exception", type(e).__name__, str(e))
        return FetcherValidator.build_error_response(error_msg)


def fetch_perf(c):
    """AWS-only performance data (no local fallback).

    STRICT MODE: Trade counts (total, winning, losing) are critical finance metrics.
    Returns 0 for missing counts is catastrophically misleading.
    """
    from tools.dashboard.fetcher_validator import FetcherValidator

    try:
        data = api_call("/api/algo/performance")
        perf = data

        # Check for API error - 503 means no performance data yet (fail-fast: return error)
        is_error, error_msg = FetcherValidator.check_api_error(perf)
        if is_error:
            record_data_quality_issue("per", "api_call", "api_error", error_msg)
            return FetcherValidator.build_error_response(error_msg)

        # Comprehensive validation using FetcherValidator
        required_fields = ["total_trades", "winning_trades", "losing_trades"]
        valid, validation_error = FetcherValidator.validate_response(
            response=perf,
            required_fields=required_fields,
            source_name="fetch_perf",
            max_age_seconds=3600,
            timestamp_field="timestamp",
        )
        if not valid:
            logger.error(validation_error)
            for field in required_fields:
                if field not in perf or perf[field] is None:
                    record_data_quality_issue("per", field, "missing_required_field")
            return FetcherValidator.build_error_response(validation_error)

        # Data is already validated at boundary; direct conversion
        n = int(perf["total_trades"])
        w = int(perf["winning_trades"])
        losing = int(perf["losing_trades"])

        equity_vals = safe_get_list(perf.get("equity_vals"))
        recent_rets = safe_get_list(perf.get("recent_rets"))

        return {
            "n": n,
            "w": w,
            "l": losing,
            "wr": perf.get("win_rate_pct"),
            "open_count": perf.get("open_losses_count") or perf.get("open_positions"),
            "pnl": perf.get("total_pnl_dollars"),
            "unrealized_pnl": perf.get("unrealized_pnl"),
            "streak": perf.get("current_streak"),
            "sharpe": perf.get("sharpe_annualized"),
            "maxdd": perf.get("max_drawdown_pct"),
            "avg_win": perf.get("avg_win_pct"),
            "avg_loss": perf.get("avg_loss_pct"),
            "profit_factor": perf.get("profit_factor"),
            "expectancy": perf.get("expectancy_r"),
            "avg_r": perf.get("expectancy_r"),
            "equity_vals": equity_vals,
            "recent_rets": recent_rets,
        }
    except Exception as e:
        error_msg = _format_fetcher_error("perf", e)
        logger.error(error_msg)
        record_data_quality_issue("per", "exception", type(e).__name__, str(e))
        return {"_error": error_msg}


def fetch_perf_analytics(c):
    """API-only performance analytics. Fail-fast: error only on failure."""
    from tools.dashboard.fetcher_validator import FetcherValidator

    try:
        data = api_call(_get_endpoint_path("perf_anl"))

        # Check for API error
        is_error, error_msg = FetcherValidator.check_api_error(data)
        if is_error:
            record_data_quality_issue("perf_anl", "api_call", "api_error", error_msg)
            return FetcherValidator.build_error_response(error_msg)

        d = data
        return {
            "sharpe252": float(d.get("rolling_sharpe_252d")),
            "sortino": float(d.get("rolling_sortino_252d")),
            "calmar": float(d.get("calmar_ratio")),
            "wr50": float(d.get("win_rate_50t")),
            "avg_w_r": float(d.get("avg_win_r_50t")),
            "avg_l_r": float(d.get("avg_loss_r_50t")),
            "expectancy": float(d.get("expectancy")),
            "maxdd": float(d.get("max_drawdown_pct")),
        }
    except Exception as e:
        error_msg = _format_fetcher_error("perf_anl", e)
        logger.error(error_msg)
        record_data_quality_issue("perf_anl", "exception", type(e).__name__, str(e))
        return FetcherValidator.build_error_response(error_msg)
