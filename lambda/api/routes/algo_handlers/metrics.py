"""Route: algo"""

import logging
import math
from datetime import datetime, timedelta, timezone

import psycopg2
import psycopg2.errors
import psycopg2.extras
import psycopg2.sql

# Ensure imports work - setup_imports is imported by parent module (lambda_function or api_router)
from routes.utils import (
    db_route_handler,
    error_response,
    handle_db_error,
    json_response,
    safe_dict_convert,
    success_response,
)

from utils.validation import (
    APIResponseValidator,
    safe_float,
    safe_float_strict,
    safe_int,
)


logger = logging.getLogger(__name__)



@db_route_handler("get algo metrics")
def _get_algo_metrics(cur) -> dict:
    """Get daily algo metrics (total actions, entries, exits)."""
    try:
        cur.execute("""
            SELECT date, total_actions, entries, exits, avg_signal_score
            FROM algo_metrics_daily
            ORDER BY date DESC
            LIMIT 1
        """)
        row = cur.fetchone()
        if row is None:
            return success_response(
                {
                    "date": None,
                    "total_actions": None,
                    "entries": None,
                    "exits": None,
                    "avg_signal_score": None,
                }
            )
        data = safe_dict_convert(row)
        return success_response(
            {
                "date": data.get("date"),
                "total_actions": safe_int(data.get("total_actions")),
                "entries": safe_int(data.get("entries")),
                "exits": safe_int(data.get("exits")),
                "avg_signal_score": safe_float_strict(data.get("avg_signal_score")),
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
def _get_algo_performance(cur) -> dict:
    """Get comprehensive algo performance metrics from pre-computed daily snapshot.

    Queries latest row from algo_performance_metrics table (computed daily by
    compute_performance_metrics.py at 4:45 PM ET). Returns in ~20ms instead
    of 8+ seconds of on-the-fly calculation.
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

    if not row:
        # Fallback: compute basic stats directly from algo_trades when pre-computed table is empty
        try:
            cur.execute("""
                SELECT
                    COUNT(*) AS total_trades,
                    COUNT(*) FILTER (WHERE profit_loss_pct > 0) AS winning_trades,
                    COUNT(*) FILTER (WHERE profit_loss_pct < 0) AS losing_trades,
                    COUNT(*) FILTER (WHERE profit_loss_pct = 0) AS breakeven_trades,
                    ROUND(AVG(CASE WHEN profit_loss_pct > 0 THEN profit_loss_pct END)::numeric, 2) AS avg_win_pct,
                    ROUND(AVG(CASE WHEN profit_loss_pct < 0 THEN profit_loss_pct END)::numeric, 2) AS avg_loss_pct,
                    ROUND(COALESCE(SUM(profit_loss_dollars), 0)::numeric, 2) AS total_pnl_dollars,
                    ROUND(AVG(CASE WHEN exit_r_multiple > 0 THEN exit_r_multiple END)::numeric, 3) AS avg_win_r,
                    ROUND(AVG(CASE WHEN exit_r_multiple < 0 THEN exit_r_multiple END)::numeric, 3) AS avg_loss_r,
                    ROUND(MAX(profit_loss_pct)::numeric, 2) AS best_trade_pct,
                    ROUND(MIN(profit_loss_pct)::numeric, 2) AS worst_trade_pct
                FROM algo_trades
                WHERE status = 'closed' AND exit_date IS NOT NULL
            """)
            fb = cur.fetchone()
            fb = safe_dict_convert(fb) if fb else {}
            total_fb_raw = fb.get("total_trades")
            total_fb = int(total_fb_raw) if total_fb_raw is not None else 0
            if total_fb == 0:
                return error_response(503, "no_data", "Performance metrics not yet available")
            winning_fb_raw = fb.get("winning_trades")
            winning_fb = int(winning_fb_raw) if winning_fb_raw is not None else 0
            losing_fb_raw = fb.get("losing_trades")
            losing_fb = int(losing_fb_raw) if losing_fb_raw is not None else 0
            wr_fb = round(winning_fb / total_fb * 100, 1) if total_fb else None
            avg_win_r = safe_float(fb.get("avg_win_r"))
            avg_loss_r = safe_float(fb.get("avg_loss_r"))
            exp_r = None
            if wr_fb is not None and avg_win_r is not None and avg_loss_r is not None:
                exp_r = round((wr_fb / 100) * avg_win_r + (1 - wr_fb / 100) * avg_loss_r, 3)
            pf_fb = None
            if avg_win_r is not None and avg_loss_r is not None and avg_loss_r != 0:
                pf_fb = round(abs(avg_win_r / avg_loss_r), 2)
            breakeven_fb_raw = fb.get("breakeven_trades")
            breakeven_fb = int(breakeven_fb_raw) if breakeven_fb_raw is not None else 0
            fallback_data: dict = {
                "total_trades": total_fb,
                "winning_trades": winning_fb,
                "losing_trades": losing_fb,
                "breakeven_trades": breakeven_fb,
                "win_rate_pct": wr_fb,
                "win_rate": wr_fb,
                "profit_factor": pf_fb,
                "total_pnl_dollars": safe_float_strict(fb.get("total_pnl_dollars")),
                "avg_win_pct": safe_float_strict(fb.get("avg_win_pct")),
                "avg_loss_pct": safe_float_strict(fb.get("avg_loss_pct")),
                "avg_win_r": avg_win_r,
                "avg_loss_r": avg_loss_r,
                "best_trade_pct": safe_float_strict(fb.get("best_trade_pct")),
                "worst_trade_pct": safe_float_strict(fb.get("worst_trade_pct")),
                "sharpe_annualized": None,
                "max_drawdown_pct": None,
                "expectancy_r": exp_r,
                "current_streak": 0,
                "equity_vals": [],
                "recent_rets": [],
                "data_freshness": {"is_stale": False},
            }
            return json_response(200, APIResponseValidator.sanitize_response(fallback_data))
        except Exception as fb_err:
            logger.warning(f"Performance fallback from algo_trades failed: {fb_err}")
            return error_response(503, "no_data", "Performance metrics not yet available")

    try:

        metrics = safe_dict_convert(row)
        total_trades_raw = metrics.get("total_trades")
        winning_raw = metrics.get("winning_trades")
        losing_raw = metrics.get("losing_trades")
        breakeven_raw = metrics.get("breakeven_trades")

        total_trades = int(total_trades_raw) if total_trades_raw is not None else None
        winning = int(winning_raw) if winning_raw is not None else None
        losing = int(losing_raw) if losing_raw is not None else None
        breakeven = int(breakeven_raw) if breakeven_raw is not None else None
        win_loss_total = (winning if winning is not None else 0) + (losing if losing is not None else 0)

        # Compute trade-level metrics missing from algo_performance_metrics
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
        except Exception as te:
            logger.warning(f"Could not compute trade-level stats: {te}")

        # Compute current win/loss streak from most recent closed trades
        current_streak = 0
        try:
            cur.execute("""
                    SELECT profit_loss_pct FROM algo_trades
                    WHERE status = 'closed' AND exit_date IS NOT NULL AND profit_loss_pct IS NOT NULL
                    ORDER BY exit_date DESC, trade_id DESC LIMIT 30
                """)
            recent_trades = cur.fetchall()
            if recent_trades:
                first_pnl = float(recent_trades[0]["profit_loss_pct"] or 0)
                is_win_streak = first_pnl > 0
                for t in recent_trades:
                    pnl = float(t["profit_loss_pct"] or 0)
                    if is_win_streak and pnl > 0:
                        current_streak += 1
                    elif not is_win_streak and pnl <= 0:
                        current_streak -= 1
                    else:
                        break
        except Exception as ce:
            logger.warning(f"Could not compute current streak: {ce}")

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
                open_losses_count = safe_int(pos_row["open_losses"])
                if open_losses_count is None:
                    open_losses_count = 0
                total_open_losses_dollars = safe_float(pos_row["total_losses"])
                if total_open_losses_dollars is None:
                    total_open_losses_dollars = 0.0
                wr = safe_float(metrics.get("win_rate_pct"))
                if open_losses_count > 0 and wr is not None:
                    total_adj = winning + losing + open_losses_count + breakeven
                    win_rate_pct_adjusted = round(
                        (winning / total_adj * 100) if total_adj > 0 else wr, 1
                    )
        except Exception as pe:
            logger.warning(f"Could not compute open losses: {pe}")

        # Compute expectancy_r from win_rate and average R multiples
        expectancy_r = None
        try:
            wr = safe_float(metrics.get("win_rate_pct"))
            avg_wr = safe_float(trade_stats.get("avg_win_r"))
            avg_lr = safe_float(trade_stats.get("avg_loss_r"))
            if wr is not None and avg_wr is not None and avg_lr is not None:
                wr_frac = wr / 100
                expectancy_r = round(wr_frac * avg_wr + (1 - wr_frac) * avg_lr, 3)
        except Exception as e:

            raise RuntimeError(f"Unexpected error: {e}") from e

        # Equity curve values from portfolio snapshots for sparkline and recent returns strip
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
                equity_vals = [
                    float(r["total_portfolio_value"])
                    for r in snap_rows
                    if r.get("total_portfolio_value") is not None
                ]
                # Last 10 in chronological order; panel takes [-5:] for the 5 most recent
                recent_rets = [
                    [
                        r["snapshot_date"].isoformat()
                        if hasattr(r["snapshot_date"], "isoformat")
                        else str(r["snapshot_date"]),
                        float(r["daily_return_pct"])
                        if r.get("daily_return_pct") is not None
                        else 0.0,
                    ]
                    for r in snap_rows[-10:]
                ]
        except Exception as eq_err:
            logger.warning(f"Could not fetch equity sparkline data for performance: {eq_err}")

        response_data = {
            "total_trades": total_trades,
            "winning_trades": winning,
            "losing_trades": losing,
            "breakeven_trades": breakeven,
            "win_rate": safe_float_strict(metrics.get("win_rate_pct")),
            "win_rate_pct": safe_float_strict(metrics.get("win_rate_pct")),
            "win_rate_pct_adjusted": win_rate_pct_adjusted,
            "win_rate_confidence": (
                "high"
                if win_loss_total >= 30
                else ("medium" if win_loss_total >= 10 else "low")
            ),
            "profit_factor": safe_float_strict(metrics.get("profit_factor")),
            "total_pnl_dollars": safe_float_strict(metrics.get("total_pnl_dollars")),
            "total_pnl_pct": safe_float_strict(metrics.get("total_pnl_pct")),
            "total_return_pct": safe_float_strict(metrics.get("cagr_pct")),
            "avg_trade_pct": safe_float_strict(metrics.get("avg_trade_pct")),
            "avg_win_pct": safe_float_strict(trade_stats.get("avg_win_pct")),
            "avg_loss_pct": safe_float_strict(trade_stats.get("avg_loss_pct")),
            "avg_win_r": safe_float_strict(trade_stats.get("avg_win_r")),
            "avg_loss_r": safe_float_strict(trade_stats.get("avg_loss_r")),
            "gross_win_dollars": safe_float_strict(trade_stats.get("gross_win_dollars")),
            "gross_loss_dollars": safe_float_strict(trade_stats.get("gross_loss_dollars")),
            "open_losses_count": open_losses_count,
            "total_open_losses_dollars": total_open_losses_dollars,
            "best_trade_pct": safe_float_strict(metrics.get("best_trade_pct")),
            "worst_trade_pct": safe_float_strict(metrics.get("worst_trade_pct")),
            "sharpe_annualized": safe_float_strict(metrics.get("sharpe_ratio")),
            "sharpe_ratio": safe_float_strict(metrics.get("sharpe_ratio")),
            "sharpe_confidence": "high",
            "sortino_annualized": safe_float_strict(metrics.get("sortino_ratio")),
            "sortino_ratio": safe_float_strict(metrics.get("sortino_ratio")),
            "max_drawdown_pct": safe_float_strict(metrics.get("max_drawdown_pct")),
            "calmar_ratio": safe_float_strict(metrics.get("calmar_ratio")),
            "expectancy_r": expectancy_r,
            "avg_hold_days": safe_float_strict(metrics.get("avg_holding_days")),
            "avg_holding_days": safe_float_strict(metrics.get("avg_holding_days")),
            "portfolio_snapshots": len(equity_vals),
            "best_win_streak": int(metrics.get("best_win_streak")) if metrics.get("best_win_streak") is not None else None,
            "worst_loss_streak": int(metrics.get("worst_loss_streak")) if metrics.get("worst_loss_streak") is not None else None,
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
def _get_algo_portfolio(cur) -> dict:
    """Get latest portfolio snapshot data with structured unrealized PnL breakdown."""
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
        if row is None:
            return success_response(
                {
                    "total_portfolio_value": None,
                    "total_cash": None,
                    "position_count": 0,
                    "daily_return_pct": None,
                    "unrealized_pnl": {
                        "total_dollars": 0.0,
                        "total_pct": 0.0,
                        "winning_positions": 0,
                        "losing_positions": 0,
                        "breakeven_positions": 0,
                        "source": "open_positions_only",
                        "note": "Includes only open positions (no closed trades, no dividends)",
                    },
                    "cumulative_return_pct": None,
                    "max_drawdown_pct": None,
                    "largest_position_pct": None,
                    "last_run": None,
                }
            )
        data = safe_dict_convert(row)
        pv = safe_float_strict(data.get("total_portfolio_value"))
        return success_response(
            {
                "total_portfolio_value": pv,
                "total_cash": safe_float_strict(data.get("total_cash")),
                "position_count": safe_int(data.get("position_count")),
                "daily_return_pct": safe_float_strict(data.get("daily_return_pct")),
                "unrealized_pnl": {
                    "total_dollars": safe_float_strict(data.get("unrealized_pnl_total")),
                    "total_pct": safe_float_strict(data.get("unrealized_pnl_pct")),
                    "winning_positions": safe_int(
                        data.get("unrealized_pnl_winning_count")
                    ),
                    "losing_positions": safe_int(
                        data.get("unrealized_pnl_losing_count")
                    ),
                    "breakeven_positions": safe_int(
                        data.get("unrealized_pnl_breakeven_count")
                    ),
                    "source": data.get("unrealized_pnl_source", "open_positions_only"),
                    "note": "Includes only open positions (no closed trades, no dividends)",
                },
                "cumulative_return_pct": safe_float_strict(data.get("cumulative_return_pct")),
                "max_drawdown_pct": safe_float_strict(data.get("max_drawdown_pct")),
                "largest_position_pct": safe_float_strict(data.get("largest_position_pct")),
                "last_run": data.get("snapshot_date"),
            }
        )
    except Exception as e:
        logger.error(f"Portfolio fetch error: {type(e).__name__}: {e}")
        return error_response(503, "service_unavailable", "Portfolio data unavailable")



@db_route_handler("get daily return histogram")
def _get_daily_return_histogram(cur) -> dict:
    """Return histogram of daily portfolio returns with stats."""
    cur.execute("""
        SELECT daily_return_pct
        FROM algo_portfolio_snapshots
        WHERE daily_return_pct IS NOT NULL
        ORDER BY snapshot_date DESC
        LIMIT 250
    """)
    rows = cur.fetchall()
    returns = [
        float(r["daily_return_pct"])
        for r in rows
        if r.get("daily_return_pct") is not None
    ]

    if not returns:
        return json_response(200, {"buckets": [], "stats": None})

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
        {"mid": round(mid, 2), "count": count}
        for mid, count in sorted(buckets_dict.items())
    ]

    mean_ret = sum(returns) / len(returns)
    variance = sum((r - mean_ret) ** 2 for r in returns) / len(returns)
    std_ret = math.sqrt(variance)
    stats = {
        "count": len(returns),
        "mean": round(mean_ret, 2),
        "std": round(std_ret, 2),
    }

    return json_response(200, {"buckets": buckets, "stats": stats})



@db_route_handler("get holding period distribution")
def _get_holding_period_distribution(cur) -> dict:
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
    durations = [
        int(r["trade_duration_days"])
        for r in rows
        if r.get("trade_duration_days") is not None
    ]

    if not durations:
        return json_response(200, {"buckets": []})

    buckets = [
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
    return json_response(200, {"buckets": filtered_buckets})



@db_route_handler("get performance analytics")
def _get_performance_analytics(cur) -> dict:
    """Get performance analytics data."""
    _null_response = {
        "rolling_sharpe_252d": None,
        "rolling_sortino_252d": None,
        "calmar_ratio": None,
        "win_rate_50t": None,
        "avg_win_r_50t": None,
        "avg_loss_r_50t": None,
        "expectancy": None,
        "max_drawdown_pct": None,
    }
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
        if row is None:
            return success_response(_null_response)
        data = safe_dict_convert(row)
        return success_response(
            {
                "rolling_sharpe_252d": safe_float_strict(data.get("rolling_sharpe_252d")),
                "rolling_sortino_252d": safe_float_strict(data.get("rolling_sortino_252d")),
                "calmar_ratio": safe_float_strict(data.get("calmar_ratio")),
                "win_rate_50t": safe_float_strict(data.get("win_rate_50t")),
                "avg_win_r_50t": safe_float_strict(data.get("avg_win_r_50t")),
                "avg_loss_r_50t": safe_float_strict(data.get("avg_loss_r_50t")),
                "expectancy": safe_float_strict(data.get("expectancy")),
                "max_drawdown_pct": safe_float_strict(data.get("max_drawdown_pct")),
            }
        )
    except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn):
        try:
            cur.execute("ROLLBACK TO SAVEPOINT perf_analytics")
        except Exception as e:

            raise RuntimeError(f"Unexpected error: {e}") from e
        return success_response(_null_response)
    except (psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
        try:
            cur.execute("ROLLBACK TO SAVEPOINT perf_analytics")
        except Exception as e:

            raise RuntimeError(f"Unexpected error: {e}") from e
        code, error_type, message = handle_db_error(e, "fetch performance analytics")
        return error_response(code, error_type, message)



@db_route_handler("get performance metrics endpoint")
def _get_performance_metrics_endpoint(cur) -> dict:
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
            "winRate": (
                safe_float_strict(row["win_rate_pct"]) / 100 if row["win_rate_pct"] else None
            ),
            "profitFactor": safe_float_strict(row["profit_factor"]),
            "expectancy": safe_float_strict(row["avg_trade_pct"]),
            "sharpeRatio": safe_float_strict(row["sharpe_ratio"]),
            "maxDrawdown": (
                safe_float_strict(row["max_drawdown_pct"]) / 100
                if row["max_drawdown_pct"]
                else None
            ),
        },
    )



@db_route_handler("get portfolio summary")
def _get_portfolio_summary(cur) -> dict:
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

    if not row.get("total_portfolio_value"):
        return error_response(
            503, "incomplete_data", "Portfolio snapshot missing required fields"
        )

    total_value = safe_float_strict(row["total_portfolio_value"])
    cash = safe_float_strict(row["total_cash"])
    invested = safe_float_strict(row["total_equity"])
    positions = safe_int(row["position_count"])
    daily_return_pct = safe_float_strict(row["daily_return_pct"])

    daily_change_dollars = (
        (daily_return_pct / 100 * total_value)
        if total_value and daily_return_pct
        else None
    )

    return json_response(
        200,
        {
            "totalValue": round(total_value, 2) if total_value else None,
            "cash": round(cash, 2) if cash else None,
            "invested": round(invested, 2) if invested else None,
            "positions": positions or 0,
            "dailyChange": (
                round(daily_change_dollars, 2) if daily_change_dollars else None
            ),
            "dailyChangePercent": (
                round(daily_return_pct, 2) if daily_return_pct else None
            ),
        },
    )

@db_route_handler("get risk metrics")
def _get_risk_metrics(cur) -> dict:
    """Get portfolio risk metrics."""
    _null_response = {
        "report_date": None,
        "var_pct_95": None,
        "cvar_pct_95": None,
        "stressed_var_pct": None,
        "portfolio_beta": None,
        "top_5_concentration": None,
    }
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
        if row is None:
            return success_response(_null_response)
        data = safe_dict_convert(row)
        return success_response(
            {
                "report_date": data.get("report_date"),
                "var_pct_95": safe_float_strict(data.get("var_pct_95")),
                "cvar_pct_95": safe_float_strict(data.get("cvar_pct_95")),
                "stressed_var_pct": safe_float_strict(data.get("stressed_var_pct")),
                "portfolio_beta": safe_float_strict(data.get("portfolio_beta")),
                "top_5_concentration": safe_float_strict(data.get("top_5_concentration")),
            }
        )
    except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn):
        try:
            cur.execute("ROLLBACK TO SAVEPOINT risk_metrics")
        except Exception as e:

            raise RuntimeError(f"Unexpected error: {e}") from e
        return success_response(_null_response)
    except (psycopg2.OperationalError, psycopg2.DatabaseError, Exception) as e:
        try:
            cur.execute("ROLLBACK TO SAVEPOINT risk_metrics")
        except Exception as e:

            raise RuntimeError(f"Unexpected error: {e}") from e
        code, error_type, message = handle_db_error(e, "fetch risk metrics")
        return error_response(code, error_type, message)



@db_route_handler("get stage distribution")
def _get_stage_distribution(cur) -> dict:
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
        return json_response(200, {"distribution": []})

    distribution = [{"phase": r["phase"], "count": safe_int(r["count"])} for r in rows]

    return json_response(200, {"distribution": distribution})



@db_route_handler("get trade distribution")
def _get_trade_distribution(cur) -> dict:
    """Return distribution of trade outcomes by R-multiple."""
    cur.execute("""
        SELECT exit_r_multiple
        FROM algo_trades
        WHERE exit_r_multiple IS NOT NULL AND status = 'closed'
        ORDER BY exit_date DESC
        LIMIT 500
    """)
    rows = cur.fetchall()
    r_multiples = [
        float(r["exit_r_multiple"])
        for r in rows
        if r.get("exit_r_multiple") is not None
    ]

    if not r_multiples:
        return json_response(200, {"buckets": []})

    buckets = [
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
    return json_response(200, {"buckets": filtered_buckets})



