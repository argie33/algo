"""Route: algo"""

# mypy: disable-error-code=no-any-return

import logging
import math
from datetime import datetime, timedelta, timezone
from typing import Any

import psycopg2
import psycopg2.errors
import psycopg2.extras
import psycopg2.sql
from psycopg2.extensions import cursor

# Ensure imports work - setup_imports is imported by parent module (lambda_function or api_router)
from routes.utils import (
    db_route_handler,
    ensure_valid_response,
    error_response,
    handle_db_error,
    json_response,
    list_response,
    safe_dict_convert,
    success_response,
)

from utils.validation import (
    APIResponseValidator,
    format_decimal_string,
)

logger = logging.getLogger(__name__)


def _ensure_portfolio_fields(data: dict) -> Any:
    """Validate portfolio response has all required fields. Fail-fast if missing.

    CRITICAL: Portfolio value and cash must never be None - they're essential for trading.
    If data is missing, return error instead of adding defaults.
    """
    if not isinstance(data, dict):
        return data

    if data.get("_error"):
        return data

    # FAIL-FAST: Critical fields must exist and be non-None
    required_fields = ["total_portfolio_value", "total_cash", "position_count"]
    for field in required_fields:
        if field not in data:
            return {"_error": f"Portfolio critical field missing: {field}"}
        if data[field] is None:
            return {"_error": f"Portfolio critical field is None: {field}"}

    return data


@db_route_handler("get algo metrics")
def _get_algo_metrics(cur: cursor) -> Any:
    """Get daily algo metrics (total actions, entries, exits). Fail-fast if unavailable."""
    try:
        cur.execute("""
            SELECT date, total_actions, entries, exits, avg_signal_score
            FROM algo_metrics_daily
            ORDER BY date DESC
            LIMIT 1
        """)
        row = cur.fetchone()
        # FAIL-FAST: Return error if metrics not yet available (no runs yet)
        if row is None:
            return error_response(
                503,
                "no_data",
                "Algo metrics not yet available - no daily runs have completed",
            )
        data = safe_dict_convert(row)

        # Validate critical fields
        date = data.get("date")
        total_actions = data.get("total_actions")
        entries = data.get("entries")
        exits = data.get("exits")

        if date is None:
            return error_response(503, "incomplete_data", "Algo metrics date missing")
        if total_actions is None or entries is None or exits is None:
            return error_response(
                503,
                "incomplete_data",
                "Algo metrics incomplete (missing actions/entries/exits)",
            )

        total_actions = int(total_actions)
        entries = int(entries)
        exits = int(exits)

        avg_signal_score_raw = data.get("avg_signal_score")
        avg_signal_score: float | None = None
        if avg_signal_score_raw is not None:
            try:
                avg_signal_score = float(avg_signal_score_raw)
            except (ValueError, TypeError) as e:
                logger.warning(f"Cannot convert avg_signal_score to float: {avg_signal_score_raw} ({e})")

        return success_response(
            {
                "date": date,
                "total_actions": total_actions,
                "entries": entries,
                "exits": exits,
                "avg_signal_score": avg_signal_score,
            }
        )
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        code, error_type, message = handle_db_error(e, "fetch algo metrics")
        return error_response(code, error_type, message)


@db_route_handler("calculate performance")
def _get_algo_performance(cur: cursor) -> Any:
    """Get comprehensive algo performance metrics from pre-computed daily snapshot.

    Queries latest row from algo_performance_metrics table (computed daily by
    compute_performance_metrics.py at 4:45 PM ET). Returns in ~20ms instead
    of 8+ seconds of on-the-fly calculation.

    FAIL-FAST: Returns error if pre-computed metrics are unavailable.
    Do NOT fall back to computing stats - that masks data loading issues.
    """
    cur.execute("""
            SELECT
                metric_date, total_trades, winning_trades, losing_trades, breakeven_trades,
                win_rate_pct, profit_factor, total_pnl_dollars, total_pnl_pct, avg_trade_pct,
                best_trade_pct, worst_trade_pct, avg_holding_days, sharpe_ratio, sortino_ratio,
                max_drawdown_pct, calmar_ratio, cagr_pct, best_win_streak, worst_loss_streak
            FROM algo_performance_metrics
            ORDER BY metric_date DESC
            LIMIT 1
        """)
    row = cur.fetchone()

    # FAIL-FAST: Return error immediately if pre-computed metrics unavailable
    # Do NOT fall back to computing from algo_trades - that masks data loader issues
    if not row:
        logger.warning(
            "Performance metrics unavailable: algo_performance_metrics table empty. "
            "Pre-computed metrics should be generated daily at 4:45 PM ET by compute_performance_metrics.py. "
            "Check data loader health."
        )
        return error_response(
            503,
            "data_unavailable",
            "Performance metrics not pre-computed. Check data loader health.",
        )

    try:
        metrics = safe_dict_convert(row)
        total_trades_raw = metrics.get("total_trades")
        winning_raw = metrics.get("winning_trades")
        losing_raw = metrics.get("losing_trades")
        breakeven_raw = metrics.get("breakeven_trades")

        # Validate critical trade count fields exist and are non-None
        if total_trades_raw is None or winning_raw is None or losing_raw is None:
            logger.error(
                f"Performance metrics incomplete: total_trades={total_trades_raw}, "
                f"winning_trades={winning_raw}, losing_trades={losing_raw} (breakeven={breakeven_raw})"
            )
            return error_response(
                503,
                "incomplete_data",
                "Performance metrics missing required trade counts",
            )

        total_trades = int(total_trades_raw)
        winning = int(winning_raw)
        losing = int(losing_raw)
        breakeven = int(breakeven_raw) if breakeven_raw is not None else 0
        win_loss_total = winning + losing

        # Compute trade-level metrics missing from algo_performance_metrics (CRITICAL for performance panel)
        trade_stats = {}
        try:
            cur.execute("""
                    SELECT
                        AVG(CASE WHEN profit_loss_pct > 0 THEN profit_loss_pct END) AS avg_win_pct,
                        AVG(CASE WHEN profit_loss_pct < 0 THEN profit_loss_pct END) AS avg_loss_pct,
                        AVG(CASE WHEN exit_r_multiple > 0 THEN exit_r_multiple END) AS avg_win_r,
                        AVG(CASE WHEN exit_r_multiple < 0 THEN exit_r_multiple END) AS avg_loss_r,
                        COALESCE(SUM(CASE WHEN profit_loss_dollars > 0 THEN profit_loss_dollars ELSE 0 END), 0) AS gross_win_dollars,
                        COALESCE(ABS(SUM(CASE WHEN profit_loss_dollars < 0 THEN profit_loss_dollars ELSE 0 END)), 0) AS gross_loss_dollars
                    FROM algo_trades
                    WHERE status = 'closed' AND exit_date IS NOT NULL
                """)
            ts_row = cur.fetchone()
            if ts_row:
                trade_stats = safe_dict_convert(ts_row)
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as te:
            logger.error(f"CRITICAL: Could not compute trade-level stats: {te}")
            return error_response(
                503,
                "data_unavailable",
                f"Trade metrics unavailable: {type(te).__name__}",
            )

        # Compute current win/loss streak from most recent closed trades (CRITICAL for performance panel)
        current_streak = 0
        try:
            cur.execute("""
                    SELECT profit_loss_pct FROM algo_trades
                    WHERE status = 'closed' AND exit_date IS NOT NULL AND profit_loss_pct IS NOT NULL
                    ORDER BY exit_date DESC, trade_id DESC LIMIT 30
                """)
            recent_trades = cur.fetchall()
            if recent_trades:
                first_pnl_raw = recent_trades[0]["profit_loss_pct"]
                if first_pnl_raw is None:
                    first_pnl = None
                else:
                    first_pnl = float(first_pnl_raw)
                if first_pnl is not None:
                    is_win_streak = first_pnl > 0
                    for t in recent_trades:
                        pnl_raw = t["profit_loss_pct"]
                        if pnl_raw is None:
                            break
                        pnl = float(pnl_raw)
                        if is_win_streak and pnl > 0:
                            current_streak += 1
                        elif not is_win_streak and pnl <= 0:
                            current_streak -= 1
                        else:
                            break
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as ce:
            logger.error(f"CRITICAL: Could not compute current streak: {ce}")
            return error_response(
                503,
                "data_unavailable",
                f"Streak computation failed: {type(ce).__name__}",
            )

        # Compute open losses for adjusted win rate
        open_losses_count = 0
        total_open_losses_dollars = 0.0
        win_rate_pct_adjusted = None
        try:
            cur.execute("""
                    SELECT
                        COUNT(*) FILTER (WHERE unrealized_pnl < 0) AS open_losses,
                        COALESCE(SUM(CASE WHEN unrealized_pnl < 0 THEN unrealized_pnl ELSE 0 END), 0) AS total_losses
                    FROM algo_positions
                    WHERE status = 'open' AND quantity > 0
                """)
            pos_row = cur.fetchone()
            if pos_row:
                open_losses_count = int(pos_row["open_losses"])
                if open_losses_count is None:
                    open_losses_count = 0
                total_open_losses_dollars = float(pos_row["total_losses"])
                if total_open_losses_dollars is None:
                    total_open_losses_dollars = 0.0
                win_rate_val = metrics.get("win_rate_pct")
                wr = float(win_rate_val) if win_rate_val is not None else None
                if open_losses_count > 0 and wr is not None:
                    win_count = winning if winning is not None else 0
                    lose_count = losing if losing is not None else 0
                    break_count = breakeven if breakeven is not None else 0
                    total_adj = win_count + lose_count + open_losses_count + break_count
                    win_rate_pct_adjusted = round((win_count / total_adj * 100) if total_adj > 0 else wr, 1)
        except (ValueError, ZeroDivisionError, TypeError) as pe:
            logger.warning(f"Could not compute open losses: {pe}")

        # Compute expectancy_r from win_rate and average R multiples
        expectancy_r = None
        try:
            win_rate_val = metrics.get("win_rate_pct")
            wr = float(win_rate_val) if win_rate_val is not None else None
            avg_wr_val = trade_stats.get("avg_win_r")
            avg_wr = float(avg_wr_val) if avg_wr_val is not None else None
            avg_lr_val = trade_stats.get("avg_loss_r")
            avg_lr = float(avg_lr_val) if avg_lr_val is not None else None
            if wr is not None and avg_wr is not None and avg_lr is not None:
                wr_frac = wr / 100
                expectancy_r = round(wr_frac * avg_wr + (1 - wr_frac) * avg_lr, 3)
        except (ValueError, ZeroDivisionError, TypeError) as e:
            raise RuntimeError(f"Unexpected error: {e}") from e

        # Equity curve values from portfolio snapshots for sparkline and recent returns strip (CRITICAL for performance panel)
        equity_vals: list = []
        recent_rets: list = []
        try:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).date()
            cur.execute(
                """
                SELECT snapshot_date, total_portfolio_value, daily_return_pct
                FROM algo_portfolio_snapshots
                WHERE snapshot_date >= %s AND total_portfolio_value > 0
                ORDER BY snapshot_date ASC
                """,
                (cutoff,),
            )
            snap_rows = cur.fetchall()
            if snap_rows:
                equity_vals = []
                missing_portfolio_values = []
                for i, r in enumerate(snap_rows):
                    if "total_portfolio_value" not in r:
                        raise RuntimeError(
                            f"[METRICS] Snapshot row {i} missing 'total_portfolio_value' field. Database query failed."
                        )
                    pv = r["total_portfolio_value"]
                    if pv is None:
                        snap_date = r.get("snapshot_date", f"unknown (row {i})")
                        missing_portfolio_values.append(snap_date)
                        continue
                    equity_vals.append(float(pv))

                if missing_portfolio_values:
                    logger.warning(
                        f"[METRICS] {len(missing_portfolio_values)} snapshots have NULL total_portfolio_value: "
                        f"{missing_portfolio_values[:3]}{'...' if len(missing_portfolio_values) > 3 else ''}. "
                        "Equity curve will have gaps."
                    )

                # Last 10 in chronological order; panel takes [-5:] for the 5 most recent
                recent_rets = [
                    [
                        (
                            r["snapshot_date"].isoformat()
                            if hasattr(r["snapshot_date"], "isoformat")
                            else str(r["snapshot_date"])
                        ),
                        (float(r["daily_return_pct"]) if r.get("daily_return_pct") is not None else None),
                    ]
                    for r in snap_rows[-10:]
                ]
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as eq_err:
            logger.error(f"CRITICAL: Could not fetch equity sparkline data for performance: {eq_err}")
            return error_response(
                503,
                "data_unavailable",
                f"Portfolio snapshot data unavailable: {type(eq_err).__name__}",
            )
        except (ValueError, ZeroDivisionError, TypeError) as eq_err:
            logger.error(f"CRITICAL: Equity data format error: {eq_err}")
            return error_response(
                500,
                "data_format_error",
                f"Portfolio data format invalid: {type(eq_err).__name__}",
            )

        fds = format_decimal_string  # Shorthand for readability
        response_data = {
            "total_trades": total_trades,
            "winning_trades": winning,
            "losing_trades": losing,
            "breakeven_trades": breakeven,
            "win_rate": fds(metrics.get("win_rate_pct"), 2, True),
            "win_rate_pct": fds(metrics.get("win_rate_pct"), 2, True),
            "win_rate_pct_adjusted": fds(win_rate_pct_adjusted, 1, True),
            "win_rate_confidence": ("high" if win_loss_total >= 30 else ("medium" if win_loss_total >= 10 else "low")),
            "profit_factor": fds(metrics.get("profit_factor"), 2, True),
            "total_pnl_dollars": fds(metrics.get("total_pnl_dollars"), 2, True),
            "total_pnl_pct": fds(metrics.get("total_pnl_pct"), 2, True),
            "total_return_pct": fds(metrics.get("cagr_pct"), 2, True),
            "avg_trade_pct": fds(metrics.get("avg_trade_pct"), 2, True),
            "avg_win_pct": fds(trade_stats.get("avg_win_pct"), 2, True),
            "avg_loss_pct": fds(trade_stats.get("avg_loss_pct"), 2, True),
            "avg_win_r": fds(trade_stats.get("avg_win_r"), 3, True),
            "avg_loss_r": fds(trade_stats.get("avg_loss_r"), 3, True),
            "gross_win_dollars": fds(trade_stats.get("gross_win_dollars"), 2, True),
            "gross_loss_dollars": fds(trade_stats.get("gross_loss_dollars"), 2, True),
            "open_losses_count": open_losses_count,
            "total_open_losses_dollars": fds(total_open_losses_dollars, 2, True),
            "best_trade_pct": fds(metrics.get("best_trade_pct"), 2, True),
            "worst_trade_pct": fds(metrics.get("worst_trade_pct"), 2, True),
            "sharpe_annualized": fds(metrics.get("sharpe_ratio"), 3, True),
            "sharpe_ratio": fds(metrics.get("sharpe_ratio"), 3, True),
            "sharpe_confidence": "high",
            "sortino_annualized": fds(metrics.get("sortino_ratio"), 3, True),
            "sortino_ratio": fds(metrics.get("sortino_ratio"), 3, True),
            "max_drawdown_pct": fds(metrics.get("max_drawdown_pct"), 2, True),
            "calmar_ratio": fds(metrics.get("calmar_ratio"), 3, True),
            "expectancy_r": fds(expectancy_r, 3, True),
            "avg_hold_days": fds(metrics.get("avg_holding_days"), 1, True),
            "avg_holding_days": fds(metrics.get("avg_holding_days"), 1, True),
            "portfolio_snapshots": len(equity_vals),
            "best_win_streak": (
                int(best_win_streak_val)
                if (best_win_streak_val := metrics.get("best_win_streak")) is not None
                else None
            ),
            "worst_loss_streak": (
                int(worst_loss_streak_val)
                if (worst_loss_streak_val := metrics.get("worst_loss_streak")) is not None
                else None
            ),
            "current_streak": current_streak,
            "equity_vals": equity_vals,
            "recent_rets": recent_rets,
            "stale_alerts": [],
            "data_freshness": {"is_stale": False},
            "confidence_metadata": {
                "sharpe_confidence": "high",
                "win_rate_confidence": "high" if win_loss_total >= 30 else "medium",
                "return_confidence": "high",
                "snapshot_count": len(equity_vals),
                "total_trades": total_trades,
            },
        }
        sanitized = APIResponseValidator.sanitize_response(response_data)

        # Validate performance response matches contract schema
        ensure_valid_response("perf", sanitized)

        return json_response(200, sanitized)
    except (
        psycopg2.errors.UndefinedTable,
        psycopg2.errors.UndefinedColumn,
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        Exception,
    ) as e:
        code, error_type, message = handle_db_error(e, "fetch performance metrics")
        return error_response(code, error_type, message)


@db_route_handler("get algo portfolio")
def _get_algo_portfolio(cur: cursor) -> Any:
    """Get latest portfolio snapshot data with structured unrealized PnL breakdown.

    FAIL-FAST: Returns error if portfolio snapshots are unavailable.
    No placeholder/fallback data - portfolio value is critical for trading.
    """
    try:
        cur.execute("""
            SELECT snapshot_date, total_portfolio_value, total_cash,
                   unrealized_pnl_total, position_count, daily_return_pct, unrealized_pnl_pct,
                   cumulative_return_pct, max_drawdown_pct, largest_position_pct,
                   unrealized_pnl_winning_count, unrealized_pnl_losing_count, unrealized_pnl_breakeven_count,
                   unrealized_pnl_source
            FROM algo_portfolio_snapshots
            ORDER BY snapshot_date DESC
            LIMIT 1
        """)
        row = cur.fetchone()
        # FAIL-FAST: Return error if no portfolio snapshots available (no trading activity yet)
        if row is None:
            logger.warning(
                "Portfolio snapshot unavailable: algo_portfolio_snapshots table empty. "
                "No snapshot created yet - algo may not have executed or data loader issue."
            )
            return error_response(
                503,
                "data_unavailable",
                "Portfolio snapshots not available yet. Check data loader health.",
            )
        data = safe_dict_convert(row)
        pv = format_decimal_string(data.get("total_portfolio_value"), precision=2, allow_none=True)
        position_count_val = data.get("position_count")
        position_count = int(position_count_val) if position_count_val is not None else 0
        winning_count_val = data.get("unrealized_pnl_winning_count")
        winning_count = int(winning_count_val) if winning_count_val is not None else 0
        losing_count_val = data.get("unrealized_pnl_losing_count")
        losing_count = int(losing_count_val) if losing_count_val is not None else 0
        breakeven_count_val = data.get("unrealized_pnl_breakeven_count")
        breakeven_count = int(breakeven_count_val) if breakeven_count_val is not None else 0

        # Calculate data_age_seconds from snapshot_date
        snapshot_date = data.get("snapshot_date")
        data_age_seconds = None
        if snapshot_date:
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc)
            snapshot_dt = snapshot_date if hasattr(snapshot_date, 'tzinfo') else (
                datetime.fromisoformat(str(snapshot_date)).replace(tzinfo=timezone.utc) if isinstance(snapshot_date, str) else None
            )
            if snapshot_dt:
                data_age_seconds = int((now - snapshot_dt).total_seconds())

        response_data = {
            "total_portfolio_value": pv,
            "total_cash": format_decimal_string(data.get("total_cash"), precision=2, allow_none=True),
            "position_count": position_count,
            "daily_return_pct": format_decimal_string(data.get("daily_return_pct"), precision=2, allow_none=True),
            "unrealized_pnl": {
                "total_dollars": format_decimal_string(data.get("unrealized_pnl_total"), precision=2, allow_none=True),
                "total_pct": format_decimal_string(data.get("unrealized_pnl_pct"), precision=2, allow_none=True),
                "winning_positions": winning_count,
                "losing_positions": losing_count,
                "breakeven_positions": breakeven_count,
                "source": data.get("unrealized_pnl_source", "open_positions_only"),
                "note": "Includes only open positions (no closed trades, no dividends)",
            },
            "cumulative_return_pct": format_decimal_string(
                data.get("cumulative_return_pct"), precision=2, allow_none=True
            ),
            "max_drawdown_pct": format_decimal_string(data.get("max_drawdown_pct"), precision=2, allow_none=True),
            "largest_position_pct": format_decimal_string(
                data.get("largest_position_pct"), precision=2, allow_none=True
            ),
            "last_run": data.get("snapshot_date"),
            "data_age_seconds": data_age_seconds,
        }
        validated_data = _ensure_portfolio_fields(response_data)

        # Validate portfolio response matches contract schema
        ensure_valid_response("port", validated_data)

        return success_response(validated_data)
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        logger.error(f"CRITICAL: Portfolio fetch database error: {type(e).__name__}: {e}")
        return error_response(503, "data_unavailable", f"Portfolio data unavailable: {type(e).__name__}")
    except (ValueError, ZeroDivisionError, TypeError) as e:
        logger.error(f"CRITICAL: Portfolio data format error: {type(e).__name__}: {e}")
        return error_response(
            500,
            "data_format_error",
            f"Portfolio data format invalid: {type(e).__name__}",
        )
    except (AttributeError, KeyError) as e:
        logger.error(
            f"CRITICAL: Portfolio fetch unexpected error: {type(e).__name__}: {e}",
            exc_info=True,
        )
        return error_response(503, "service_error", f"Portfolio service error: {type(e).__name__}")


@db_route_handler("get daily return histogram")
def _get_daily_return_histogram(cur: cursor) -> Any:
    """Return histogram of daily portfolio returns with stats."""
    cur.execute("""
        SELECT daily_return_pct
        FROM algo_portfolio_snapshots
        WHERE daily_return_pct IS NOT NULL
        ORDER BY snapshot_date DESC
        LIMIT 250
    """)
    rows = cur.fetchall()
    returns = [float(r["daily_return_pct"]) for r in rows if r.get("daily_return_pct") is not None]

    if not returns:
        response = list_response([], total=0, limit=None, offset=None)
        response["data"]["stats"] = None
        return response

    bucket_width = 0.5
    min_ret = min(returns)
    max_ret = max(returns)
    min_bucket = math.floor(min_ret / bucket_width) * bucket_width
    max_bucket = math.ceil(max_ret / bucket_width) * bucket_width

    buckets_dict = {}
    mid = min_bucket
    while mid <= max_bucket:
        buckets_dict[mid] = 0
        mid += bucket_width

    for ret in returns:
        bucket_mid = round(ret / bucket_width) * bucket_width
        if bucket_mid in buckets_dict:
            buckets_dict[bucket_mid] += 1

    buckets = [
        {"mid": format_decimal_string(mid, precision=2), "count": count} for mid, count in sorted(buckets_dict.items())
    ]

    mean_ret = sum(returns) / len(returns)
    variance = sum((r - mean_ret) ** 2 for r in returns) / len(returns)
    std_ret = math.sqrt(variance)
    stats = {
        "count": len(returns),
        "mean": format_decimal_string(mean_ret, precision=2),
        "std": format_decimal_string(std_ret, precision=2),
    }

    response = list_response(buckets, total=len(buckets), limit=None, offset=None)
    response["data"]["stats"] = stats
    return response


@db_route_handler("get holding period distribution")
def _get_holding_period_distribution(cur: cursor) -> Any:
    """Return distribution of position holding periods in days."""
    cur.execute("""
        SELECT CASE
            WHEN trade_duration_days IS NOT NULL AND trade_duration_days > 0 THEN trade_duration_days
            ELSE (exit_date - trade_date)::int
        END AS trade_duration_days
        FROM algo_trades
        WHERE status = 'closed' AND exit_date IS NOT NULL
        ORDER BY exit_date DESC
        LIMIT 500
    """)
    rows = cur.fetchall()
    durations = [int(r["trade_duration_days"]) for r in rows if r.get("trade_duration_days") is not None]

    if not durations:
        return list_response([], total=0, limit=None, offset=None)

    buckets: list[dict[str, Any]] = [
        {"range": "0-3 days", "count": 0},
        {"range": "4-7 days", "count": 0},
        {"range": "8-14 days", "count": 0},
        {"range": "15-30 days", "count": 0},
        {"range": "31-60 days", "count": 0},
        {"range": "61-90 days", "count": 0},
        {"range": "91-180 days", "count": 0},
        {"range": ">180 days", "count": 0},
    ]

    for d in durations:
        if d <= 3:
            buckets[0]["count"] += 1
        elif d <= 7:
            buckets[1]["count"] += 1
        elif d <= 14:
            buckets[2]["count"] += 1
        elif d <= 30:
            buckets[3]["count"] += 1
        elif d <= 60:
            buckets[4]["count"] += 1
        elif d <= 90:
            buckets[5]["count"] += 1
        elif d <= 180:
            buckets[6]["count"] += 1
        else:
            buckets[7]["count"] += 1

    filtered_buckets = [b for b in buckets if b["count"] > 0]
    return list_response(filtered_buckets, total=len(filtered_buckets), limit=None, offset=None)


@db_route_handler("get performance analytics")
def _get_performance_analytics(cur: cursor) -> Any:
    """Get performance analytics data. Fail-fast if unavailable."""
    try:
        cur.execute("SAVEPOINT perf_analytics")
        cur.execute("""
            SELECT rolling_sharpe_252d, rolling_sortino_252d, calmar_ratio,
                   win_rate_50t, avg_win_r_50t, avg_loss_r_50t, expectancy, max_drawdown_pct
            FROM algo_performance_daily
            ORDER BY report_date DESC
            LIMIT 1
        """)
        row = cur.fetchone()
        cur.execute("RELEASE SAVEPOINT perf_analytics")
        # FAIL-FAST: Return error if no performance analytics available
        if row is None:
            logger.warning(
                "Performance analytics unavailable: algo_performance_daily table empty. "
                "Check data loader health - should be populated daily."
            )
            return error_response(
                503,
                "data_unavailable",
                "Performance analytics not available. Check data loader health.",
            )
        data = safe_dict_convert(row)
        sharpe: Any = data.get("rolling_sharpe_252d")
        sortino: Any = data.get("rolling_sortino_252d")
        calmar: Any = data.get("calmar_ratio")
        wr_50t: Any = data.get("win_rate_50t")
        avg_wr: Any = data.get("avg_win_r_50t")
        avg_lr: Any = data.get("avg_loss_r_50t")
        expectancy_val: Any = data.get("expectancy")
        max_dd: Any = data.get("max_drawdown_pct")
        response_dict = {
            "rolling_sharpe_252d": float(sharpe) if sharpe is not None else None,
            "rolling_sortino_252d": float(sortino) if sortino is not None else None,
            "calmar_ratio": float(calmar) if calmar is not None else None,
            "win_rate_50t": float(wr_50t) if wr_50t is not None else None,
            "avg_win_r_50t": float(avg_wr) if avg_wr is not None else None,
            "avg_loss_r_50t": float(avg_lr) if avg_lr is not None else None,
            "expectancy": (float(expectancy_val) if expectancy_val is not None else None),
            "max_drawdown_pct": float(max_dd) if max_dd is not None else None,
        }
        response_dict["sharpe252"] = response_dict["rolling_sharpe_252d"]
        response_dict["sortino"] = response_dict["rolling_sortino_252d"]
        response_dict["calmar"] = response_dict["calmar_ratio"]
        return success_response(response_dict)
    except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn):
        try:
            cur.execute("ROLLBACK TO SAVEPOINT perf_analytics")
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(f"Unexpected error: {e}") from e
        logger.error("Performance analytics table missing or schema changed")
        return error_response(503, "table_missing", "Performance analytics table not found")
    except (
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        ValueError,
        KeyError,
    ) as e:
        try:
            cur.execute("ROLLBACK TO SAVEPOINT perf_analytics")
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as save_err:
            raise RuntimeError(f"Savepoint rollback failed: {save_err}") from save_err
        code, error_type, message = handle_db_error(e, "fetch performance analytics")
        return error_response(code, error_type, message)


@db_route_handler("get performance metrics endpoint")
def _get_performance_metrics_endpoint(cur: cursor) -> Any:
    """Return latest performance metrics."""
    cur.execute("""
        SELECT win_rate_pct, profit_factor, avg_trade_pct, sharpe_ratio, max_drawdown_pct
        FROM algo_performance_metrics
        ORDER BY metric_date DESC
        LIMIT 1
    """)
    row = cur.fetchone()

    if not row:
        return error_response(503, "no_data", "Performance metrics not yet available")

    return json_response(
        200,
        {
            "win_rate": (float(row["win_rate_pct"]) / 100 if row["win_rate_pct"] else None),
            "profit_factor": float(row["profit_factor"]),
            "expectancy": float(row["avg_trade_pct"]),
            "sharpe_ratio": float(row["sharpe_ratio"]),
            "max_drawdown": (float(row["max_drawdown_pct"]) / 100 if row["max_drawdown_pct"] else None),
        },
    )


@db_route_handler("get portfolio summary")
def _get_portfolio_summary(cur: cursor) -> Any:
    """Return portfolio summary with current value and allocation."""
    cur.execute("""
        SELECT total_portfolio_value, total_cash, total_equity, position_count, daily_return_pct
        FROM algo_portfolio_snapshots
        ORDER BY snapshot_date DESC
        LIMIT 1
    """)
    row = cur.fetchone()

    if not row:
        return error_response(503, "no_data", "Portfolio snapshot not yet available")

    # Validate critical fields (fail-fast: check for None, not falsiness - 0.0 is valid)
    total_value_raw = row.get("total_portfolio_value")
    if total_value_raw is None:
        return error_response(503, "incomplete_data", "Portfolio snapshot missing total_portfolio_value")

    try:
        total_value = float(total_value_raw)
        cash = float(row["total_cash"])
        invested = float(row["total_equity"])
        positions = int(row["position_count"])
        daily_return_pct = float(row["daily_return_pct"])
    except (ValueError, TypeError) as e:
        logger.error(f"Cannot convert portfolio fields to numeric types: {e}")
        return error_response(503, "incomplete_data", "Portfolio snapshot has invalid numeric fields")

    daily_change_dollars = (daily_return_pct / 100 * total_value) if total_value and daily_return_pct else None

    if positions is None:
        return json_response(
            200,
            {
                "total_value": round(total_value, 2) if total_value else None,
                "cash": round(cash, 2) if cash else None,
                "invested": round(invested, 2) if invested else None,
                "positions": None,
                "_warning": "positions count unavailable",
                "daily_change": (round(daily_change_dollars, 2) if daily_change_dollars else None),
                "daily_change_percent": (round(daily_return_pct, 2) if daily_return_pct else None),
            },
        )

    return json_response(
        200,
        {
            "total_value": round(total_value, 2) if total_value else None,
            "cash": round(cash, 2) if cash else None,
            "invested": round(invested, 2) if invested else None,
            "positions": positions,
            "daily_change": (round(daily_change_dollars, 2) if daily_change_dollars else None),
            "daily_change_percent": (round(daily_return_pct, 2) if daily_return_pct else None),
        },
    )


@db_route_handler("get risk metrics")
def _get_risk_metrics(cur: cursor) -> Any:
    """Get portfolio risk metrics. Fail-fast if unavailable."""
    try:
        cur.execute("SAVEPOINT risk_metrics")
        cur.execute("""
            SELECT report_date, var_pct_95, cvar_pct_95, stressed_var_pct,
                   portfolio_beta, top_5_concentration
            FROM algo_risk_daily
            ORDER BY report_date DESC
            LIMIT 1
        """)
        row = cur.fetchone()
        cur.execute("RELEASE SAVEPOINT risk_metrics")
        # FAIL-FAST: Return error if no risk metrics available
        if row is None:
            logger.warning(
                "Risk metrics unavailable: algo_risk_daily table empty. "
                "Check data loader health - should be populated daily."
            )
            return error_response(
                503,
                "data_unavailable",
                "Risk metrics not available. Check data loader health.",
            )
        data = safe_dict_convert(row)
        var_95 = data.get("var_pct_95")
        cvar_95 = data.get("cvar_pct_95")
        stressed_var = data.get("stressed_var_pct")
        portfolio_beta = data.get("portfolio_beta")
        concentration = data.get("top_5_concentration")
        return success_response(
            {
                "report_date": data.get("report_date"),
                "var_pct_95": float(var_95) if var_95 is not None else None,
                "cvar_pct_95": float(cvar_95) if cvar_95 is not None else None,
                "stressed_var_pct": (float(stressed_var) if stressed_var is not None else None),
                "svar": (float(stressed_var) if stressed_var is not None else None),
                "portfolio_beta": (float(portfolio_beta) if portfolio_beta is not None else None),
                "top_5_concentration": (float(concentration) if concentration is not None else None),
            }
        )
    except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn):
        try:
            cur.execute("ROLLBACK TO SAVEPOINT risk_metrics")
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
            raise RuntimeError(f"Unexpected error: {e}") from e
        logger.error("Risk metrics table missing or schema changed")
        return error_response(503, "table_missing", "Risk metrics table not found")
    except (
        psycopg2.OperationalError,
        psycopg2.DatabaseError,
        ValueError,
        KeyError,
    ) as e:
        try:
            cur.execute("ROLLBACK TO SAVEPOINT risk_metrics")
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as save_err:
            raise RuntimeError(f"Unexpected error: {save_err}") from save_err
        code, error_type, message = handle_db_error(e, "fetch risk metrics")
        return error_response(code, error_type, message)


@db_route_handler("get stage distribution")
def _get_stage_distribution(cur: cursor) -> Any:
    """Return distribution of positions by Weinstein stage."""
    cur.execute("""
        SELECT
            COUNT(*) as count,
            CASE
                WHEN weinstein_stage = 1 THEN 'Stage 1 (base)'
                WHEN weinstein_stage = 2 THEN
                    CASE
                        WHEN minervini_trend_score < 4 THEN 'Early Stage-2'
                        WHEN minervini_trend_score >= 6 THEN 'Late Stage-2'
                        ELSE 'Mid Stage-2'
                    END
                WHEN weinstein_stage = 3 THEN 'Stage 3 (top)'
                WHEN weinstein_stage = 4 THEN 'Stage 4 (down)'
                ELSE 'Unknown'
            END as phase
        FROM algo_positions_with_risk
        GROUP BY phase, weinstein_stage
        ORDER BY weinstein_stage ASC
    """)
    rows = cur.fetchall()

    if not rows:
        return list_response([], total=0, limit=None, offset=None)

    distribution = [{"phase": r["phase"], "count": int(r["count"])} for r in rows]

    return list_response(distribution, total=len(distribution), limit=None, offset=None)


@db_route_handler("get trade distribution")
def _get_trade_distribution(cur: cursor) -> Any:
    """Return distribution of trade outcomes by R-multiple."""
    cur.execute("""
        SELECT exit_r_multiple
        FROM algo_trades
        WHERE exit_r_multiple IS NOT NULL AND status = 'closed'
        ORDER BY exit_date DESC
        LIMIT 500
    """)
    rows = cur.fetchall()
    r_multiples = [float(r["exit_r_multiple"]) for r in rows if r.get("exit_r_multiple") is not None]

    if not r_multiples:
        return list_response([], total=0, limit=None, offset=None)

    buckets: list[dict[str, Any]] = [
        {"range": "<-2R", "count": 0, "min": -999},
        {"range": "-2R to -1R", "count": 0, "min": -2},
        {"range": "-1R to 0R", "count": 0, "min": -1},
        {"range": "0R to 1R", "count": 0, "min": 0},
        {"range": "1R to 2R", "count": 0, "min": 1},
        {"range": "2R to 3R", "count": 0, "min": 2},
        {"range": ">3R", "count": 0, "min": 3},
    ]

    for r in r_multiples:
        if r < -2:
            buckets[0]["count"] += 1
        elif r < -1:
            buckets[1]["count"] += 1
        elif r < 0:
            buckets[2]["count"] += 1
        elif r < 1:
            buckets[3]["count"] += 1
        elif r < 2:
            buckets[4]["count"] += 1
        elif r < 3:
            buckets[5]["count"] += 1
        else:
            buckets[6]["count"] += 1

    filtered_buckets = [b for b in buckets if b["count"] > 0]
    return list_response(filtered_buckets, total=len(filtered_buckets), limit=None, offset=None)
