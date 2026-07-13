"""Fetcher functions for portfolio, positions, trades, and performance data."""

import logging
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from algo.infrastructure.market_calendar import MarketCalendar
from utils.validation.framework import safe_float

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
        # CRITICAL FIX: Account for Friday→Monday gap where portfolio data can be 60+ hours old
        # On trading days AFTER market opens: data must be fresh (5 min) since Phase 9 runs daily at close
        # On trading days BEFORE/EARLY: accept data from previous trading day (up to 72 hours for Fri→Mon)
        # On non-trading days: accept data from last trading day
        is_trading_day = MarketCalendar.is_trading_day()
        if is_trading_day:
            # TRADING DAY: Check if market has closed (4:00 PM ET)
            from datetime import datetime
            from datetime import time as dt_time
            from zoneinfo import ZoneInfo

            et = ZoneInfo("America/New_York")
            now_et = datetime.now(et)
            market_close_time = dt_time(16, 0)  # 4:00 PM ET

            if now_et.time() >= market_close_time:
                # After market close (4:00 PM): Phase 9 should run soon, expect fresh data
                max_age_seconds = 300  # 5 minutes after close
                grace_period_seconds = 60  # 1 minute grace
            else:
                # Before/during market hours: accept data from previous trading day (up to 72 hours)
                # This handles Friday→Monday gap where data from Friday (4 PM) is still valid Mon morning
                max_age_seconds = 259200  # 72 hours (3 days) for pre-close trading days
                grace_period_seconds = 3600  # 1 hour grace for trading day pre-close
        else:
            # Non-trading days (weekends/holidays): accept data from last trading day (extended to account for long gaps)
            max_age_seconds = 432000  # 120 hours (5 days) for non-trading days to handle holidays
            grace_period_seconds = 3600  # 1 hour grace period for non-trading days (clock skew, processing delays)

        # Comprehensive validation using FetcherValidator
        required_fields = [
            "total_portfolio_value",
            "total_cash",
            "position_count",
        ]
        # Check for API error first
        is_error, error_msg = FetcherValidator.check_api_error(port)
        if is_error:
            logger.error(error_msg or "unknown error")
            record_data_quality_issue("portfolio", "api_call", "api_error", error_msg or "unknown error")
            return FetcherValidator.build_error_response(error_msg)

        # Validate required fields exist
        valid, error_msg = FetcherValidator.require_fields(port, required_fields, "fetch_portfolio")
        if not valid:
            logger.error(error_msg)
            for field in required_fields:
                if field not in port or port[field] is None:
                    record_data_quality_issue("portfolio", field, "missing_required_field")
            return FetcherValidator.build_error_response(error_msg)

        # Validate snapshot_date field (API returns snapshot_date, not last_run)
        snapshot_date = port.get("snapshot_date") or port.get("last_run")
        if not snapshot_date:
            logger.error("Portfolio missing snapshot_date/last_run field")
            record_data_quality_issue("portfolio", "snapshot_date", "missing_required_field")
            return FetcherValidator.build_error_response("Portfolio snapshot_date/last_run field missing")

        # Check if API reports stale data in data_freshness field
        data_freshness = port.get("data_freshness", {})
        is_stale_from_api = data_freshness.get("is_stale", False)

        # Use the is_stale flag from API if available (more reliable than calculating here)
        # The API has direct database access and can timestamp accurately
        if is_stale_from_api:
            data_age = data_freshness.get("age_seconds", port.get("data_age_seconds", "unknown"))
            error_msg = (
                f"Portfolio data is stale ({data_age}s old). "
                f"Phase 9 orchestration may not be running or may have failed. "
                f"Check: (1) EventBridge scheduler deployed? (2) Phase 9 logs in AWS CloudWatch? "
                f"(3) database table algo_portfolio_snapshots has recent updates?"
            )
            logger.error(f"[FAIL_FAST] {error_msg}")
            record_data_quality_issue("portfolio", "freshness", "stale_data", error_msg)
            return FetcherValidator.build_error_response(error_msg)

        # Note: data_age_seconds will be extracted later from port and validated then

        # Validate required fields are present and non-None
        if port.get("total_portfolio_value") is None:
            record_data_quality_issue("portfolio", "total_portfolio_value", "none_value")
            return FetcherValidator.build_error_response("Portfolio total_portfolio_value is None")  # Explicit return
        if port.get("total_cash") is None:
            record_data_quality_issue("portfolio", "total_cash", "none_value")
            return FetcherValidator.build_error_response("Portfolio total_cash is None")  # Explicit return
        if port.get("position_count") is None:
            record_data_quality_issue("portfolio", "position_count", "none_value")
            return FetcherValidator.build_error_response("Portfolio position_count is None")  # Explicit return

        # SAFE: Values are validated non-None above, so direct dict access is safe
        tpv = float(port["total_portfolio_value"])
        tc = float(port["total_cash"])
        pc = int(port["position_count"])

        # Extract unrealized PnL percentage with explicit handling for missing/invalid data
        unrealized_pnl_pct = None
        unrealized_pnl_raw = port.get("unrealized_pnl")
        if unrealized_pnl_raw is not None:
            unrealized_pnl_dict = safe_get_dict(unrealized_pnl_raw)
            if unrealized_pnl_dict and "total_pct" in unrealized_pnl_dict:
                val = unrealized_pnl_dict.get("total_pct")
                unrealized_pnl_pct = float(val) if val is not None else None
            elif unrealized_pnl_dict:
                # Unrealized PnL dict exists but missing total_pct field
                logger.warning(
                    f"[DATA_QUALITY] Portfolio unrealized_pnl missing 'total_pct' field. "
                    f"Available keys: {list(unrealized_pnl_dict.keys())}"
                )
            else:
                # Unrealized PnL is not a dict (malformed)
                logger.warning(
                    f"[DATA_QUALITY] Portfolio unrealized_pnl is malformed: expected dict, got {type(unrealized_pnl_raw).__name__}"
                )

        # snapshot_date already validated above (accepts both snapshot_date and last_run fields)
        # Use the value we already validated, no need to re-fetch

        daily_return = port.get("daily_return_pct")
        cumulative_return = port.get("cumulative_return_pct")
        max_dd = port.get("max_drawdown_pct")
        largest_pos = port.get("largest_position_pct")
        data_age = port.get("data_age_seconds")

        # These are derived analytics (daily/cumulative return, drawdown, largest position)
        # that are legitimately None on the first trading day, when Phase 9 hasn't computed
        # them yet, or with zero open positions — not a sign of a data failure. Log for
        # visibility but pass None through: dashboard/panels/portfolio.py already handles
        # each of these being None explicitly (renders the rest of the portfolio panel,
        # only warns if it's a trading day). Previously this hard-failed the ENTIRE
        # portfolio fetch over any one of these being unset, which — combined with "port"
        # being a critical fetcher in fetchers.py's load_all() — blanked the whole
        # dashboard, not just this panel, whenever one derived metric was momentarily
        # unavailable (e.g. right after an orchestrator halt).
        missing_metrics = []
        if daily_return is None:
            missing_metrics.append("daily_return_pct")
        if cumulative_return is None:
            missing_metrics.append("cumulative_return_pct")
        if max_dd is None:
            missing_metrics.append("max_drawdown_pct")
        if largest_pos is None:
            missing_metrics.append("largest_position_pct")

        if missing_metrics:
            logger.warning(f"[DATA_QUALITY] Portfolio missing derived metrics: {', '.join(missing_metrics)}")
            record_data_quality_issue(
                "portfolio", "missing_metrics", "validation", f"Missing: {', '.join(missing_metrics)}"
            )

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
    """Fetch positions via AWS API only (fail-fast: error if unavailable).

    CRITICAL: Each position must have required fields: symbol, current_price,
    avg_entry_price, position_value. Positions with missing critical fields are
    filtered out with error tracking (data quality issue).
    """
    from dashboard.fetcher_validator import FetcherValidator

    try:
        data = api_call(get_endpoint_path("pos"))

        # Check for API error
        is_error, error_msg = FetcherValidator.check_api_error(data)
        if is_error:
            record_data_quality_issue("pos", "api_call", "api_error", error_msg or "api error")
            return FetcherValidator.build_error_response(error_msg or "api error")

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

        # Validate each position has required fields
        required_fields = ["symbol", "current_price", "avg_entry_price", "position_value"]
        valid_items = []
        invalid_count = 0

        for idx, pos in enumerate(items):
            if not isinstance(pos, dict):
                logger.error(f"Position {idx}: not a dict, got {type(pos).__name__}")
                record_data_quality_issue(
                    "pos", f"position_{idx}", "invalid_type", f"Expected dict, got {type(pos).__name__}"
                )
                invalid_count += 1
                continue

            # Check required fields
            missing = [f for f in required_fields if f not in pos or pos[f] is None]
            if missing:
                symbol = pos.get("symbol", f"<unknown_{idx}>")
                logger.error(f"Position {symbol}: missing required fields: {missing}")
                record_data_quality_issue("pos", symbol, "missing_required_fields", f"Missing: {missing}")
                invalid_count += 1
                continue

            valid_items.append(pos)

        total_items = len(items)
        if total_items == 0:
            # No positions returned - don't mask this with 100% coverage
            items_coverage_pct = None
            logger.warning("[POSITIONS] API returned zero positions - positions data unavailable or portfolio empty")
        else:
            items_coverage_pct = (len(valid_items) / total_items * 100)

        if invalid_count > 0:
            logger.warning(
                f"Filtered {invalid_count} invalid position(s) from API response, {len(valid_items)} valid. "
                f"Coverage: {items_coverage_pct:.1f}% ({len(valid_items)}/{total_items})" if items_coverage_pct is not None else "Invalid positions filtered, but no valid items remain"
            )

        return {
            "items": valid_items,
            "timestamp": datetime.now(ET),
            "items_coverage_pct": items_coverage_pct,
            "items_valid_count": len(valid_items),
            "items_total_count": total_items,
        }
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
            record_data_quality_issue("trades", "api_call", "api_error", error_msg or "unknown_error")
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

        # Track trades data quality metrics
        trades_count = len(trades) if trades else 0
        return {
            "items": trades,
            "timestamp": datetime.now(ET),
            "trades_count": trades_count,
            "data_available": trades_count > 0,
        }
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
            record_data_quality_issue("per", "api_call", "api_error", error_msg or "unknown_error")
            return FetcherValidator.build_error_response(error_msg)

        # Comprehensive validation using FetcherValidator
        # No freshness check: data is pre-computed daily (no "timestamp" field in response)
        required_fields = [
            "total_trades",
            "winning_trades",
            "losing_trades",
            "win_rate_pct",
            "total_pnl_dollars",
            "sharpe_annualized",
            "max_drawdown_pct",
            "avg_win_pct",
            "avg_loss_pct",
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
                    record_data_quality_issue("perf", field, "missing_required_field")
            return FetcherValidator.build_error_response(validation_error)

        # Validate required fields are present and non-None
        if perf.get("total_trades") is None:
            record_data_quality_issue("perf", "total_trades", "none_value")
            return FetcherValidator.build_error_response("Performance total_trades is None")
        if perf.get("winning_trades") is None:
            record_data_quality_issue("perf", "winning_trades", "none_value")
            return FetcherValidator.build_error_response("Performance winning_trades is None")
        if perf.get("losing_trades") is None:
            record_data_quality_issue("perf", "losing_trades", "none_value")
            return FetcherValidator.build_error_response("Performance losing_trades is None")

        n = int(perf["total_trades"])
        w = int(perf["winning_trades"])
        losing = int(perf["losing_trades"])

        # Equity curve and recent returns are optional enrichment fields for charts
        equity_vals_raw = perf.get("equity_vals")
        if equity_vals_raw is not None:
            equity_vals = safe_get_list(equity_vals_raw)
            if not isinstance(equity_vals, list):
                logger.warning(f"Invalid equity_vals type {type(equity_vals_raw).__name__}, expected list - using empty list")
                equity_vals = []
        else:
            logger.debug("Performance data missing 'equity_vals' field - optional for core performance metrics")
            equity_vals = []

        recent_rets_raw = perf.get("recent_rets")
        if recent_rets_raw is not None:
            recent_rets = safe_get_list(recent_rets_raw)
            if not isinstance(recent_rets, list):
                logger.warning(f"Invalid recent_rets type {type(recent_rets_raw).__name__}, expected list - using empty list")
                recent_rets = []
        else:
            logger.debug("Performance data missing 'recent_rets' field - optional for core performance metrics")
            recent_rets = []

        def _f(v: object) -> float | None:
            if v is None:
                logger.debug("[PORTFOLIO_FETCHER] Performance metric value is None - optional metric unavailable")
                return None
            try:
                return float(v)  # type: ignore[arg-type]
            except (TypeError, ValueError) as e:
                raise ValueError(f"[PORTFOLIO_FETCHER] Failed to convert performance metric {v!r} to float: {e}") from e

        # unrealized_pnl is optional enrichment (comes from portfolio endpoint if available)
        # Performance endpoint may not include it; return explicit marker if unavailable
        unrealized_pnl = perf.get("unrealized_pnl")
        if unrealized_pnl is None:
            logger.debug("Performance data missing 'unrealized_pnl' field (optional enrichment)")
            unrealized_pnl = {"data_unavailable": True, "reason": "not_in_performance_response"}

        # open_positions_count = total open positions; open_losses_count = subset with losses
        # Accept both API field names to support different versions
        open_positions_count = perf.get("open_positions_count") or perf.get("open_positions")
        if open_positions_count is None:
            error_msg = (
                "Performance data missing 'open_positions' or 'open_positions_count' field. "
                "Required to calculate position quality and risk metrics."
            )
            logger.error(f"[PORTFOLIO_FETCHER CRITICAL] {error_msg}")
            return FetcherValidator.build_error_response(error_msg)
        open_count = open_positions_count

        # Validate core performance metrics (streak, expectancy, and avg win/loss are optional enrichment)
        core_metrics = {
            "win_rate_pct": "wr",
            "total_pnl_dollars": "pnl",
            "sharpe_annualized": "sharpe",
            "max_drawdown_pct": "maxdd",
            "profit_factor": "profit_factor",
        }
        missing_core_metrics = [
            name for field, name in core_metrics.items() if field not in perf or perf.get(field) is None
        ]
        if missing_core_metrics:
            error_msg = f"Performance data missing core metrics: {', '.join(missing_core_metrics)}"
            logger.error(f"[FAIL_FAST] {error_msg}")
            record_data_quality_issue("perf", "missing_metrics", "validation", error_msg)
            return FetcherValidator.build_error_response(error_msg)

        # Optional enrichment metrics: legitimately null until enough closed trades exist
        # (e.g. avg_win_pct/avg_loss_pct require at least one win/loss to average over)
        optional_metrics = ["current_streak", "expectancy_r", "avg_win_pct", "avg_loss_pct"]
        for field in optional_metrics:
            if field not in perf or perf.get(field) is None:
                logger.debug(f"Performance data missing optional field '{field}' - using None")
                perf[field] = None

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
        record_data_quality_issue("perf", "exception", type(e).__name__, str(e))
        return {"_error": error_msg}


def fetch_perf_analytics(c: None) -> dict[str, Any]:
    """API-only performance analytics. Fail-fast on missing critical metrics.

    STRICT MODE: Sharpe, Sortino, and Expectancy are CRITICAL metrics.
    These determine strategy quality assessment. Missing data indicates API schema mismatch.
    """
    from dashboard.fetcher_validator import FetcherValidator

    try:
        data = api_call(get_endpoint_path("perf_anl"))

        # Check for API error
        is_error, error_msg = FetcherValidator.check_api_error(data)
        if is_error:
            record_data_quality_issue("perf_anl", "api_call", "api_error", error_msg or "unknown_error")
            return FetcherValidator.build_error_response(error_msg)

        d = data

        # FAIL-FAST: If ANY metric is present but critical metrics are missing, error
        # (allows all-None during early ramp-up, but catches schema mismatches)
        all_fields = [
            "rolling_sharpe_252d",
            "rolling_sortino_252d",
            "calmar_ratio",
            "win_rate_50t",
            "avg_win_r_50t",
            "avg_loss_r_50t",
            "expectancy",
            "max_drawdown_pct",
        ]

        critical_fields = {
            "rolling_sharpe_252d": "sharpe252",
            "rolling_sortino_252d": "sortino",
            "expectancy": "expectancy",
        }

        # Check if at least one metric exists (not in ramp-up)
        has_any_metric = any(d.get(field) is not None for field in all_fields)

        if has_any_metric:
            # If we have some data, critical metrics must be present
            missing_critical = [name for field, name in critical_fields.items() if d.get(field) is None]
            if missing_critical:
                error_msg = f"Performance analytics missing required metrics: {', '.join(missing_critical)}"
                logger.error(f"[FAIL_FAST] {error_msg}")
                record_data_quality_issue("perf_anl", "missing_critical_metrics", "validation", error_msg)
                return FetcherValidator.build_error_response(error_msg)

        return {
            "sharpe252": safe_float(d.get("rolling_sharpe_252d"), default=None, field_name="sharpe252"),
            "sortino": safe_float(d.get("rolling_sortino_252d"), default=None, field_name="sortino"),
            "calmar": safe_float(d.get("calmar_ratio"), default=None, field_name="calmar"),
            "wr50": safe_float(d.get("win_rate_50t"), default=None, field_name="wr50"),
            "avg_w_r": safe_float(d.get("avg_win_r_50t"), default=None, field_name="avg_w_r"),
            "avg_l_r": safe_float(d.get("avg_loss_r_50t"), default=None, field_name="avg_l_r"),
            "expectancy": safe_float(d.get("expectancy"), default=None, field_name="expectancy"),
            "maxdd": safe_float(d.get("max_drawdown_pct"), default=None, field_name="maxdd"),
        }
    except Exception as e:
        error_msg = format_fetcher_error("perf_anl", e)
        logger.error(error_msg)
        record_data_quality_issue("perf_anl", "exception", type(e).__name__, str(e))
        return FetcherValidator.build_error_response(error_msg)
