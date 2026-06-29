"""Fetcher functions for portfolio, positions, trades, and performance data."""

import logging
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from algo.infrastructure.market_calendar import MarketCalendar
from utils.safe_data_conversion import safe_float

from .api_data_layer import api_call
from .fetcher_validator import FetcherValidator
from .fetchers_common import format_fetcher_error, get_endpoint_path, record_data_quality_issue
from .panels.data_extractors import safe_get_dict, safe_get_list

ET = ZoneInfo("America/New_York")
logger = logging.getLogger(__name__)






def fetch_portfolio(c: None) -> dict[str, Any]:
    """Fetch portfolio snapshot from API. Fails clean if unavailable.

    STRICT MODE: Uses direct conversion for critical financial fields (no defaults to 0).
    Missing data triggers error, not silent 0 values which are catastrophically misleading.

    NOTE: Portfolio data is updated by Phase 9 daily reconciliation. If data is stale
    (>7 days old), Phase 9 orchestration may be halted or failed — check orchestration
    logs and algo_portfolio_snapshots table for recent updates.

    Non-trading days: On weekends and holidays, portfolio data is NOT updated because
    Phase 9 only runs during trading days. Freshness check is relaxed on non-trading days
    to accept data from the last trading day.
    """
    try:
        data = api_call("/api/algo/portfolio")
        port = data

        # Determine appropriate max_age_seconds based on market status
        # On trading days: data must be fresh (5 min) since Phase 9 runs daily
        # On non-trading days: accept data from last trading day
        # - Weekend/single-day gap: 48 hours (2 days)
        # - Extended gap (Monday morning before market opens): 72 hours (3 days for Friday→Monday)
        is_trading_day = MarketCalendar.is_trading_day()
        if is_trading_day:
            max_age_seconds = 300  # 5 minutes for trading days
            grace_period_seconds = 60  # 1 minute grace for trading days
        else:
            # Non-trading days: accept data from last trading day (extended to account for holidays/long weekends)
            max_age_seconds = 432000  # 120 hours (5 days) for non-trading days to handle extended gaps
            grace_period_seconds = 3600  # 1 hour grace period for non-trading days (clock skew, processing delays)

        # Comprehensive validation using FetcherValidator
        required_fields = [
            "total_portfolio_value",
            "total_cash",
            "position_count",
            "last_run",
        ]
        # Check for API error first
        is_error, error_msg = FetcherValidator.check_api_error(port)
        if is_error:
            logger.error(error_msg)
            record_data_quality_issue("portfolio", "api_call", "api_error", error_msg)
            return FetcherValidator.build_error_response(error_msg)

        # Validate required fields exist
        valid, error_msg = FetcherValidator.require_fields(port, required_fields, "fetch_portfolio")
        if not valid:
            logger.error(error_msg)
            for field in required_fields:
                if field not in port or port[field] is None:
                    record_data_quality_issue("portfolio", field, "missing_required_field")
            return FetcherValidator.build_error_response(error_msg)

        # Use the API-calculated data_age_seconds field for freshness check
        # (avoids date parsing issues and trusts the API's calculation)
        data_age = port.get("data_age_seconds")
        max_age_with_grace = max_age_seconds + grace_period_seconds

        # FAIL: Data exceeds maximum acceptable age
        if data_age is not None and data_age > max_age_with_grace:
            error_msg = f"Data is stale ({data_age}s old, max {max_age_with_grace}s including grace period)"
            logger.error(error_msg)
            record_data_quality_issue("portfolio", "freshness", "stale_data", error_msg)
            return FetcherValidator.build_error_response(error_msg)

        # WARN: Data is older than 24 hours but still within acceptable range
        # This flag indicates portfolio data hasn't been updated in a while (non-trading day gap)
        # Check Phase 9 reconciliation logs if concerned.
        hours_24_seconds = 86400
        is_stale_24h = data_age is not None and data_age > hours_24_seconds
        if is_stale_24h:
            logger.warning(
                f"[DATA_QUALITY] Portfolio data is {data_age}s old ({data_age / 3600:.1f} hours). "
                f"This is normal on non-trading days but unexpected on trading days. "
                f"Check Phase 9 reconciliation if this persists. Data is still within limits ({max_age_with_grace}s), "
                f"but monitor for staleness."
            )
            record_data_quality_issue("portfolio", "freshness", "stale_warning_24h")

        # Data is already validated at boundary; direct conversion
        tpv = float(port["total_portfolio_value"])
        tc = float(port["total_cash"])
        pc = int(port["position_count"])

        unrealized_pnl_dict = safe_get_dict(port.get("unrealized_pnl"))
        unrealized_pnl_pct = None
        if unrealized_pnl_dict and "total_pct" in unrealized_pnl_dict:
            val = unrealized_pnl_dict.get("total_pct")
            unrealized_pnl_pct = float(val) if val is not None else None
        elif port.get("unrealized_pnl") is not None:
            logger.warning(
                f"[DATA_QUALITY] Portfolio unrealized_pnl missing 'total_pct' field. "
                f"Available keys: {list(unrealized_pnl_dict.keys()) if unrealized_pnl_dict else 'None'}"
            )

        # Validate optional fields have reasonable values when present
        snapshot_date = port.get("last_run")
        if not snapshot_date:
            logger.warning("[DATA_QUALITY] Portfolio snapshot_date is missing (last_run not set)")

        daily_return = port.get("daily_return_pct")
        cumulative_return = port.get("cumulative_return_pct")
        max_dd = port.get("max_drawdown_pct")
        largest_pos = port.get("largest_position_pct")
        data_age = port.get("data_age_seconds")

        return {
            "snapshot_date": snapshot_date,
            "total_portfolio_value": tpv,
            "total_cash": tc,
            "position_count": pc,
            "daily_return_pct": daily_return,
            "unrealized_pnl_pct": unrealized_pnl_pct,
            "cumulative_return_pct": cumulative_return,
            "max_drawdown_pct": max_dd,
            "largest_position_pct": largest_pos,
            "data_age_seconds": data_age,
        }
    except Exception as e:
        error_msg = format_fetcher_error("port", e)
        logger.error(error_msg)
        record_data_quality_issue("portfolio", "exception", type(e).__name__, str(e))
        return FetcherValidator.build_error_response(error_msg)


def fetch_positions(c: None) -> dict[str, Any]:
    """Fetch positions via AWS API only (fail-fast: error if unavailable)."""
    from dashboard.fetcher_validator import FetcherValidator

    try:
        data = api_call(get_endpoint_path("pos"))

        # Check for API error
        is_error, error_msg = FetcherValidator.check_api_error(data)
        if is_error:
            record_data_quality_issue("pos", "api_call", "api_error", error_msg)
            return FetcherValidator.build_error_response(error_msg)

        result = data
        if isinstance(result, dict):
            items = result.get("items")
            if items is None:
                error_msg = "Positions API response: 'items' field is missing"
                logger.error(error_msg)
                record_data_quality_issue("pos", "validation", "items_missing")
                return FetcherValidator.build_error_response(error_msg)
            if not isinstance(items, list):
                error_msg = f"Positions API response: 'items' field is not a list, got {type(items).__name__}"
                logger.error(error_msg)
                record_data_quality_issue("pos", "validation", "items_not_list")
                return FetcherValidator.build_error_response(error_msg)
        elif isinstance(result, list):
            items = result
        else:
            error_msg = f"Positions API response: expected dict or list, got {type(result).__name__}"
            logger.error(error_msg)
            record_data_quality_issue("pos", "validation", "invalid_response_type")
            return FetcherValidator.build_error_response(error_msg)
        return {"items": items, "timestamp": datetime.now(ET)}
    except Exception as e:
        error_msg = format_fetcher_error("pos", e)
        logger.error(error_msg)
        record_data_quality_issue("pos", "exception", type(e).__name__, str(e))
        return FetcherValidator.build_error_response(error_msg)


def fetch_recent_trades(c: None) -> dict[str, Any]:
    """AWS-only trades data. Fail-fast: error only on failure.

    Returns closed trades only - open positions are in the positions panel.
    Note: 503 means no closed trades yet (algo just started) - treat as no data.
    """
    from dashboard.fetcher_validator import FetcherValidator

    try:
        data = api_call(
            get_endpoint_path("trades"),
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
            if trades is None:
                error_msg = "Trades API response: 'items' field is missing"
                logger.error(error_msg)
                record_data_quality_issue("trades", "validation", "items_missing")
                return FetcherValidator.build_error_response(error_msg)
            if not isinstance(trades, list):
                error_msg = f"Trades API response: 'items' field is not a list, got {type(trades).__name__}"
                logger.error(error_msg)
                record_data_quality_issue("trades", "validation", "items_not_list")
                return FetcherValidator.build_error_response(error_msg)
        elif isinstance(result, list):
            trades = result
        else:
            error_msg = f"Trades API response: expected dict or list, got {type(result).__name__}"
            logger.error(error_msg)
            record_data_quality_issue("trades", "validation", "invalid_response_type")
            return FetcherValidator.build_error_response(error_msg)
        return {"items": trades, "timestamp": datetime.now(ET)}
    except Exception as e:
        error_msg = format_fetcher_error("trades", e)
        logger.error(error_msg)
        record_data_quality_issue("trades", "exception", type(e).__name__, str(e))
        return FetcherValidator.build_error_response(error_msg)


def fetch_perf(c: None) -> dict[str, Any]:
    """AWS-only performance data (no local fallback).

    STRICT MODE: Trade counts (total, winning, losing) are critical finance metrics.
    Returns 0 for missing counts is catastrophically misleading.
    """
    from dashboard.fetcher_validator import FetcherValidator

    try:
        data = api_call("/api/algo/performance")
        perf = data

        # Check for API error - 503 means no performance data yet (fail-fast: return error)
        is_error, error_msg = FetcherValidator.check_api_error(perf)
        if is_error:
            record_data_quality_issue("per", "api_call", "api_error", error_msg)
            return FetcherValidator.build_error_response(error_msg)

        # Comprehensive validation using FetcherValidator
        # No freshness check: data is pre-computed daily (no "timestamp" field in response)
        required_fields = [
            "total_trades", "winning_trades", "losing_trades",
            "win_rate_pct", "total_pnl_dollars", "sharpe_annualized",
            "max_drawdown_pct", "avg_win_pct", "avg_loss_pct"
        ]
        valid, validation_error = FetcherValidator.validate_response(
            response=perf,
            required_fields=required_fields,
            source_name="fetch_perf",
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

        equity_vals_raw = perf.get("equity_vals")
        if equity_vals_raw is None:
            logger.error("Performance data missing 'equity_vals' field (required for equity curve rendering)")
            return FetcherValidator.build_error_response("Missing required field: equity_vals")
        equity_vals = safe_get_list(equity_vals_raw)
        if not isinstance(equity_vals, list):
            logger.error(f"Invalid equity_vals type {type(equity_vals_raw).__name__}, expected list")
            return FetcherValidator.build_error_response(f"Invalid equity_vals type: expected list, got {type(equity_vals_raw).__name__}")

        recent_rets_raw = perf.get("recent_rets")
        if recent_rets_raw is None:
            logger.error("Performance data missing 'recent_rets' field (required for recent returns display)")
            return FetcherValidator.build_error_response("Missing required field: recent_rets")
        recent_rets = safe_get_list(recent_rets_raw)
        if not isinstance(recent_rets, list):
            logger.error(f"Invalid recent_rets type {type(recent_rets_raw).__name__}, expected list")
            return FetcherValidator.build_error_response(f"Invalid recent_rets type: expected list, got {type(recent_rets_raw).__name__}")

        def _f(v: object) -> float | None:
            if v is None:
                return None
            try:
                return float(v)  # type: ignore[arg-type]
            except (TypeError, ValueError) as e:
                raise ValueError(f"Failed to convert performance metric to float: {v!r} — {e}") from e

        # unrealized_pnl is optional enrichment (comes from portfolio endpoint if available)
        # Performance endpoint may not include it; return explicit marker if unavailable
        unrealized_pnl = perf.get("unrealized_pnl")
        if unrealized_pnl is None:
            logger.debug("Performance data missing 'unrealized_pnl' field (optional enrichment)")
            unrealized_pnl = {
                "data_unavailable": True,
                "reason": "not_in_performance_response"
            }

        # CRITICAL: open_losses_count is REQUIRED. No fallback to alternative fields.
        # Missing field indicates API schema mismatch — fail-fast.
        open_losses_count = perf.get("open_losses_count")
        if open_losses_count is None:
            raise ValueError(
                "Performance data missing required field 'open_losses_count'. "
                "Available: " + str(list(perf.keys()))
            )
        open_count = open_losses_count

        return {
            "n": n,
            "w": w,
            "l": losing,
            "wr": _f(perf.get("win_rate_pct")),
            "open_count": open_count,
            "pnl": _f(perf.get("total_pnl_dollars")),
            "unrealized_pnl": unrealized_pnl,
            "streak": perf.get("current_streak"),
            "sharpe": _f(perf.get("sharpe_annualized")),
            "maxdd": _f(perf.get("max_drawdown_pct")),
            "avg_win": _f(perf.get("avg_win_pct")),
            "avg_loss": _f(perf.get("avg_loss_pct")),
            "profit_factor": _f(perf.get("profit_factor")),
            "expectancy": _f(perf.get("expectancy_r")),
            "avg_r": _f(perf.get("expectancy_r")),
            "equity_vals": equity_vals,
            "recent_rets": recent_rets,
        }
    except Exception as e:
        error_msg = format_fetcher_error("perf", e)
        logger.error(error_msg)
        record_data_quality_issue("per", "exception", type(e).__name__, str(e))
        return {"_error": error_msg}


def fetch_perf_analytics(c: None) -> dict[str, Any]:
    """API-only performance analytics. Fail-fast: error only on failure.

    STRICT MODE: Performance metrics (Sharpe, Sortino, Expectancy, etc.) are CRITICAL.
    Missing data indicates API schema mismatch or computation failure.
    No fallback to None—must raise to surface the issue to operators.
    """
    from dashboard.fetcher_validator import FetcherValidator

    try:
        data = api_call(get_endpoint_path("perf_anl"))

        # Check for API error
        is_error, error_msg = FetcherValidator.check_api_error(data)
        if is_error:
            record_data_quality_issue("perf_anl", "api_call", "api_error", error_msg)
            return FetcherValidator.build_error_response(error_msg)

        d = data

        # CRITICAL: Performance metrics are NOT informational — they are fundamental to portfolio analysis.
        # These metrics (Sharpe, Sortino, Calmar, Max Drawdown, Win Rate, Avg Win/Loss, Expectancy)
        # determine strategy quality and operator awareness. Missing or invalid metrics must fail-fast
        # so operators are immediately alerted to data loading failures. Silent None values mask
        # NOTE: Performance analytics is non-critical dashboard metric (not used for trading decisions).
        # Use strict=False to gracefully handle None/missing values instead of failing hard.
        # Critical metrics (VaR, risk) use strict=True; informational metrics (Sharpe, Sortino) use strict=False.

        # Extract metrics with explicit logging for missing optional fields
        optional_fields = {
            "rolling_sharpe_252d": "sharpe252",
            "rolling_sortino_252d": "sortino",
            "calmar_ratio": "calmar",
            "win_rate_50t": "wr50",
            "avg_win_r_50t": "avg_w_r",
            "avg_loss_r_50t": "avg_l_r",
            "expectancy": "expectancy",
            "max_drawdown_pct": "maxdd",
        }

        for api_field, _display_name in optional_fields.items():
            if api_field not in d:
                logger.debug(f"[DATA_QUALITY] Performance analytics missing optional '{api_field}'")

        return {
            "sharpe252": safe_float(d.get("rolling_sharpe_252d"), strict=False, field_name="sharpe252"),
            "sortino": safe_float(d.get("rolling_sortino_252d"), strict=False, field_name="sortino"),
            "calmar": safe_float(d.get("calmar_ratio"), strict=False, field_name="calmar"),
            "wr50": safe_float(d.get("win_rate_50t"), strict=False, field_name="wr50"),
            "avg_w_r": safe_float(d.get("avg_win_r_50t"), strict=False, field_name="avg_w_r"),
            "avg_l_r": safe_float(d.get("avg_loss_r_50t"), strict=False, field_name="avg_l_r"),
            "expectancy": safe_float(d.get("expectancy"), strict=False, field_name="expectancy"),
            "maxdd": safe_float(d.get("max_drawdown_pct"), strict=False, field_name="maxdd"),
        }
    except Exception as e:
        error_msg = format_fetcher_error("perf_anl", e)
        logger.error(error_msg)
        record_data_quality_issue("perf_anl", "exception", type(e).__name__, str(e))
        return FetcherValidator.build_error_response(error_msg)
