"""Algo metrics handler: /api/algo/performance.

Split 2026-09-05 (file-size-ratchet compliance split of the original 1246-line
algo_handlers/metrics.py into a package, one module per top-level handler function -
same pattern as loaders/stock_scores/ and lambda/api/routes/algo_handlers/dashboard/).
This module holds only `_get_algo_performance`; the other handlers live in their own
sibling modules (or, for `_get_portfolio_summary`, directly in `__init__.py` - see
that file's docstring for why). `_compute_data_age_seconds` (shared with
`performance_analytics.py`) lives in `_shared.py`. All names are re-exported from
`algo_handlers/metrics/__init__.py` so existing callers (e.g. routes/algo.py's
`from .algo_handlers.metrics import (...)`) require zero changes. Pure move, no
logic changed - body is byte-for-byte identical to the pre-split version (only the
import header differs, trimmed to this function's actual dependencies).
"""

from __future__ import annotations

# mypy: disable-error-code=no-any-return
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import psycopg2
import psycopg2.errors
from psycopg2.extensions import cursor
from routes.utils import (
    db_route_handler,
    error_response,
    handle_db_error,
    json_response,
    safe_dict_convert,
    validate_api_response,
)

from utils.data_queries import (
    get_recent_trade_pnls,
    get_trade_performance_stats,
)
from utils.validation import (
    APIResponseValidator,
    format_decimal_string,
    get_optional_field,
)

from ._shared import _compute_data_age_seconds

logger = logging.getLogger(__name__)


@db_route_handler("calculate performance")
@validate_api_response("perf")
def _get_algo_performance(cur: cursor) -> Any:  # noqa: C901
    """Get comprehensive algo performance metrics.

    Risk ratios (Sharpe/Sortino/Calmar/max drawdown) come from algo_performance_daily,
    written every orchestrator run by Phase 9 (algo.reporting.LivePerformance -
    see algo/orchestrator/phase9_reconciliation.py::_compute_performance_metrics).
    Trade counts and win rate are computed live from algo_trades.

    NOTE: algo_performance_metrics (the table this endpoint used to read) has had no
    writer since 2026-06-30 - the compute_performance_metrics.py loader referenced in
    older comments/migrations no longer exists in this repo. Reading it served
    increasingly stale Sharpe/Sortino/Calmar/max-drawdown numbers (e.g. a 2.9% max
    drawdown next to a real, circuit-breaker-confirmed 28.75% drawdown) without any
    explicit staleness flag - a silent-fallback violation of this project's own
    data-integrity rule. algo_performance_daily is the table actually kept current;
    it lacked total_pnl_dollars until migration 1222 (2026-08-24) added it - see
    algo/reporting/performance.py's total_pnl(). It still lacks avg_holding_days,
    cagr_pct, and streaks (nothing computes these), so those are returned as None
    (all optional per the "perf" response contract) rather than served stale.

    FAIL-FAST: Raises error if metrics unavailable. No silent defaults or graceful degradation.
    Dashboard must handle 503 explicitly.
    """
    try:
        cur.execute("""
                SELECT
                    report_date AS metric_date, rolling_sharpe_252d AS sharpe_ratio,
                    rolling_sortino_252d AS sortino_ratio, max_drawdown_pct, calmar_ratio,
                    total_pnl_dollars, updated_at
                FROM algo_performance_daily
                ORDER BY report_date DESC
                LIMIT 1
            """)
        row = cur.fetchone()
    except (psycopg2.errors.UndefinedTable, psycopg2.errors.UndefinedColumn) as col_err:
        logger.error(f"Performance metrics table/columns unavailable: {col_err}")
        raise RuntimeError(f"Performance metrics schema incomplete: {col_err}") from col_err

    if not row:
        logger.error(
            "Performance metrics unavailable: algo_performance_daily table empty. "
            "Phase 9 (LivePerformance.generate_daily_report) should populate it every orchestrator run."
        )
        raise RuntimeError("Performance metrics data unavailable - table is empty")

    try:
        metrics = safe_dict_convert(row)

        # Trade counts computed live from algo_trades, not read from algo_performance_daily's
        # own total_trades/num_wins/num_losses columns (corrected 2026-08-24: those ARE
        # populated, contrary to this comment's prior claim - live-verified non-NULL). They
        # represent a different, narrower thing on purpose: win_rate()'s rolling
        # `lookback_trades` window (see algo/reporting/performance.py, column names
        # win_rate_50t/avg_win_r_50t), not the all-time lifetime count this endpoint reports.
        # The old algo_performance_metrics source for all-time counts is a dead table (see
        # above), so this query is the only live source for the true all-time total.
        try:
            cur.execute("""
                    SELECT
                        COUNT(*) FILTER (WHERE profit_loss_pct > 0) AS winning_trades,
                        COUNT(*) FILTER (WHERE profit_loss_pct < 0) AS losing_trades,
                        COUNT(*) FILTER (WHERE profit_loss_pct = 0) AS breakeven_trades,
                        COUNT(*) AS total_trades
                    FROM algo_trades
                    WHERE status = 'closed' AND exit_date IS NOT NULL
                """)
            count_row = cur.fetchone()
        except (psycopg2.DatabaseError, psycopg2.OperationalError) as ce:
            logger.error(f"CRITICAL: Could not compute live trade counts: {ce}")
            return error_response(503, "data_unavailable", f"Trade count computation failed: {type(ce).__name__}")

        if not count_row:
            logger.error("Trade count query returned no row (COUNT(*) should always return one row)")
            return error_response(503, "incomplete_data", "Trade count computation returned no data.")

        count_row = safe_dict_convert(count_row)
        total_trades = int(count_row["total_trades"])
        winning = int(count_row["winning_trades"])
        losing = int(count_row["losing_trades"])
        breakeven = int(count_row["breakeven_trades"])
        win_loss_total = winning + losing
        win_rate_pct_live = round(winning / win_loss_total * 100, 2) if win_loss_total > 0 else None

        # Compute trade-level metrics missing from algo_performance_daily (CRITICAL for performance panel)
        try:
            # Use centralized data query (single source of truth)
            trade_stats = get_trade_performance_stats(cur)
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
            # Use centralized data query (single source of truth)
            pnl_values = get_recent_trade_pnls(cur, limit=30)
            if pnl_values:
                first_pnl = float(pnl_values[0]) if pnl_values[0] is not None else None
                if first_pnl is not None:
                    is_win_streak = first_pnl > 0
                    for pnl_raw in pnl_values:
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
        open_positions_count = 0
        total_open_losses_dollars = 0.0
        try:
            cur.execute("""
                    SELECT
                        COUNT(*) AS total_open,
                        COUNT(*) FILTER (WHERE unrealized_pnl < 0) AS open_losses,
                        -- CRITICAL: Use NULLIF instead of COALESCE to detect missing position data
                        NULLIF(SUM(CASE WHEN unrealized_pnl < 0 THEN unrealized_pnl ELSE 0 END), 0) AS total_losses
                    FROM algo_positions
                    WHERE status = 'open' AND quantity > 0
                """)
            pos_row = cur.fetchone()
            if pos_row:
                pos_row = safe_dict_convert(pos_row)
                # Fail-fast: COUNT(*) always returns non-None. If total_open is None, it indicates data issue.
                # Do not silently convert to 0.
                if "total_open" not in pos_row or pos_row["total_open"] is None:
                    logger.error("Position count query failed - total_open field missing or NULL")
                    return error_response(
                        503,
                        "incomplete_position_data",
                        "Performance metrics incomplete: Cannot fetch open position count. Query returned NULL.",
                    )
                open_positions_count = int(pos_row["total_open"])
                open_losses_count_raw = pos_row["open_losses"]
                if open_losses_count_raw is None:
                    logger.error("Position data incomplete: Cannot determine open losing positions")
                    return error_response(
                        503,
                        "incomplete_position_data",
                        "Performance metrics incomplete: Cannot fetch count of open losing positions. "
                        "Query result missing 'open_losses' field. Check database and algo_positions table.",
                    )
                open_losses_count = int(open_losses_count_raw)
                total_losses_raw = pos_row["total_losses"]
                # CRITICAL: Distinguish between "no open positions" (NULL) and "zero losses" (0)
                if total_losses_raw is None:
                    if open_losses_count > 0:
                        logger.error(
                            f"Position data inconsistency: {open_losses_count} open losses found but total_losses is NULL"
                        )
                        return error_response(
                            503,
                            "data_inconsistency",
                            f"Position data inconsistent: {open_losses_count} losing positions exist but sum is missing. "
                            "Check algo_positions query and calculation.",
                        )
                    else:
                        logger.info("No open losing positions found (data quality check)")
                        total_open_losses_dollars = 0.0
                else:
                    total_open_losses_dollars = float(total_losses_raw)
                wr = win_rate_pct_live
                if open_losses_count > 0 and wr is not None:
                    win_count = winning if winning is not None else 0
                    lose_count = losing if losing is not None else 0
                    # Decisive trades only - breakeven trades excluded from the denominator,
                    # same convention as win_rate_pct_live above (winning/win_loss_total).
                    # Including them here (previous code: + break_count) would have diluted
                    # this "adjusted" win rate the same way LivePerformance.win_rate() and
                    # MetricsCalculator.calculate_win_rate did before those were fixed.
                    total_adj = win_count + lose_count + open_losses_count
                    # Adjusted win rate with open losses: (win_count / total_adj * 100)
                    # Currently unused; computed for future analytics panel enhancement
                    _ = round((win_count / total_adj * 100) if total_adj > 0 else wr, 1)
        except (ValueError, ZeroDivisionError, TypeError) as pe:
            logger.warning(f"Could not compute open losses: {pe}")

        # Compute expectancy_r from win_rate and average R multiples
        expectancy_r = None
        try:
            wr = win_rate_pct_live
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
        equity_vals: list[Any] = []
        recent_rets: list[Any] = []
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
                missing_return_pcts = []
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

                # GRACEFUL DEGRADATION: Build equity curve with available data
                # Only warn if data quality is severely degraded (>10% NULL)
                if missing_portfolio_values:
                    null_count = len(missing_portfolio_values)
                    total_snapshots = len(snap_rows)
                    null_pct = (null_count / total_snapshots * 100) if total_snapshots > 0 else 0

                    if null_pct > 10:
                        warning_msg = (
                            f"[METRICS] Equity data degraded: {null_pct:.1f}% "
                            f"({null_count}/{total_snapshots}) snapshots have NULL total_portfolio_value. "
                            f"Equity curve incomplete but displayable with {len(equity_vals)} valid values."
                        )
                        logger.warning(warning_msg)
                    else:
                        info_msg = (
                            f"[METRICS] Minor data gaps: {null_pct:.1f}% "
                            f"({null_count}/{total_snapshots}) snapshots NULL. "
                            f"Equity curve rendered with {len(equity_vals)} valid values."
                        )
                        logger.info(info_msg)

                # GRACEFUL DEGRADATION: Build recent returns with available data
                # Only warn if data quality is severely degraded (>10% NULL)
                recent_rets = []
                for r in snap_rows[-10:]:
                    daily_ret = r.get("daily_return_pct")
                    if daily_ret is None:
                        snap_date = r.get("snapshot_date", "unknown")
                        missing_return_pcts.append(snap_date)
                        continue
                    date_str = (
                        r["snapshot_date"].isoformat()
                        if hasattr(r["snapshot_date"], "isoformat")
                        else str(r["snapshot_date"])
                    )
                    recent_rets.append([date_str, float(daily_ret)])

                if missing_return_pcts:
                    null_count_rets = len(missing_return_pcts)
                    total_recent = len(snap_rows[-10:])
                    null_pct_rets = (null_count_rets / total_recent * 100) if total_recent > 0 else 0

                    if null_pct_rets > 10:
                        warning_msg = (
                            f"[METRICS] Return data degraded: {null_pct_rets:.1f}% "
                            f"({null_count_rets}/{total_recent}) recent snapshots missing daily_return_pct. "
                            f"Recent returns strip incomplete but displayable with {len(recent_rets)} valid values."
                        )
                        logger.warning(warning_msg)
                    else:
                        info_msg = (
                            f"[METRICS] Minor return data gaps: {null_pct_rets:.1f}% "
                            f"({null_count_rets}/{total_recent}) recent snapshots NULL. "
                            f"Recent returns rendered with {len(recent_rets)} valid values."
                        )
                        logger.info(info_msg)
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

        # Risk ratios come from algo_performance_daily (live, see query above).
        win_rate_pct = win_rate_pct_live
        sharpe_ratio = get_optional_field(metrics, "sharpe_ratio")
        sortino_ratio = get_optional_field(metrics, "sortino_ratio")
        max_drawdown_pct = get_optional_field(metrics, "max_drawdown_pct")
        calmar_ratio = get_optional_field(metrics, "calmar_ratio")

        # total_pnl_dollars: real, live since migration 1222 (2026-08-24) - see
        # algo/reporting/performance.py's total_pnl() and this file's docstring above.
        # total_pnl_pct/cagr_pct/avg_trade_pct/best_trade_pct still have no live source
        # (algo_performance_metrics, which used to carry them, has had no writer since
        # 2026-06-30). All optional per the "perf" response contract; None is honest, a
        # 3-week-stale number is not.
        total_pnl_dollars = get_optional_field(metrics, "total_pnl_dollars")
        total_pnl_pct = None
        cagr_pct = None
        avg_trade_pct = None
        best_trade_pct = None
        worst_trade_pct = None
        avg_holding_days = None
        best_win_streak = None
        worst_loss_streak = None

        # Extract optional trade stats fields
        avg_win_pct = get_optional_field(trade_stats, "avg_win_pct") if isinstance(trade_stats, dict) else None
        avg_loss_pct = get_optional_field(trade_stats, "avg_loss_pct") if isinstance(trade_stats, dict) else None
        avg_win_r = get_optional_field(trade_stats, "avg_win_r") if isinstance(trade_stats, dict) else None
        avg_loss_r = get_optional_field(trade_stats, "avg_loss_r") if isinstance(trade_stats, dict) else None
        gross_win_dollars = (
            get_optional_field(trade_stats, "gross_win_dollars") if isinstance(trade_stats, dict) else None
        )
        gross_loss_dollars = (
            get_optional_field(trade_stats, "gross_loss_dollars") if isinstance(trade_stats, dict) else None
        )
        # Profit factor = gross wins / gross losses, computed live from the same
        # closed-trade dollar sums (gross_loss_dollars is already NULLIF(...,0)-guarded
        # by get_trade_performance_stats, so it's None rather than 0 when there are no losses).
        profit_factor = (
            round(float(gross_win_dollars) / float(gross_loss_dollars), 2)
            if gross_win_dollars is not None and gross_loss_dollars is not None
            else None
        )

        report_date = metrics.get("metric_date")
        data_age_seconds = _compute_data_age_seconds(cur, metrics.get("updated_at"), "algo_performance_daily")

        response_data = {
            "total_trades": total_trades,
            "winning_trades": winning,
            "losing_trades": losing,
            "breakeven_trades": breakeven,
            "win_rate": fds(win_rate_pct, 2, True),
            "win_rate_pct": fds(win_rate_pct, 2, True),
            "win_rate_confidence": ("high" if win_loss_total >= 30 else ("medium" if win_loss_total >= 10 else "low")),
            "profit_factor": fds(profit_factor, 2, True),
            "total_pnl_dollars": fds(total_pnl_dollars, 2, True),
            "total_pnl_pct": fds(total_pnl_pct, 2, True),
            "total_return_pct": fds(cagr_pct, 2, True),
            "avg_trade_pct": fds(avg_trade_pct, 2, True),
            "avg_win_pct": fds(avg_win_pct, 2, True),
            "avg_loss_pct": fds(avg_loss_pct, 2, True),
            "avg_win_r": fds(avg_win_r, 3, True),
            "avg_loss_r": fds(avg_loss_r, 3, True),
            "gross_win_dollars": fds(gross_win_dollars, 2, True),
            "gross_loss_dollars": fds(gross_loss_dollars, 2, True),
            "open_positions_count": open_positions_count,
            "open_losses_count": open_losses_count,
            "total_open_losses_dollars": fds(total_open_losses_dollars, 2, True),
            "best_trade_pct": fds(best_trade_pct, 2, True),
            "worst_trade_pct": fds(worst_trade_pct, 2, True),
            "sharpe_annualized": fds(sharpe_ratio, 3, True),
            "sharpe_ratio": fds(sharpe_ratio, 3, True),
            "sharpe_confidence": "high",
            "sortino_annualized": fds(sortino_ratio, 3, True),
            "sortino_ratio": fds(sortino_ratio, 3, True),
            "max_drawdown_pct": fds(max_drawdown_pct, 2, True),
            "calmar_ratio": fds(calmar_ratio, 3, True),
            "expectancy_r": fds(expectancy_r, 3, True),
            "avg_hold_days": fds(avg_holding_days, 1, True),
            "avg_holding_days": fds(avg_holding_days, 1, True),
            "best_win_streak": int(best_win_streak) if best_win_streak is not None else None,
            "worst_loss_streak": int(worst_loss_streak) if worst_loss_streak is not None else None,
            "current_streak": current_streak,
            "equity_vals": equity_vals,
            "recent_rets": recent_rets,
            "report_date": report_date.isoformat() if report_date is not None else None,
            "data_age_seconds": data_age_seconds,
            "stale_alerts": [],
            "data_freshness": {"is_stale": data_age_seconds > 24 * 3600},
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
