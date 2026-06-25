"""
Compute algorithm performance metrics and store in algo_performance_metrics table.
Runs nightly after Phase 7 reconciliation (around 5:15 PM ET).

CRITICAL FIX (E10 - Data Integrity):
Win rate now includes OPEN TRADES based on unrealized P&L, not just closed trades.
This prevents the dashboard from showing artificially high win rates that ignore losses on open positions.

Metrics computed:
- Win/loss counts and rates (includes closed + open trades with unrealized P&L)
- Profit factor
- Sharpe ratio (annualized)
- Sortino ratio (annualized)
- Maximum drawdown %
- CAGR %
- Calmar ratio
- Avg holding days
- Best/worst streaks
"""

import logging
from datetime import date
from typing import Any

import psycopg2
import psycopg2.extras

# Add parent directory to path for imports
from utils.db.context import DatabaseContext
from utils.metrics_calculator import MetricsCalculator

logger = logging.getLogger(__name__)


def compute_performance_metrics(cur: Any, metric_date: date | None = None) -> dict[str, Any] | None:
    """Compute all performance metrics for today and store in database."""
    if metric_date is None:
        metric_date = date.today()

    try:
        metrics: dict[str, Any] = {}

        # Fetch all closed trades + open trades with unrealized P&L (E10 fix)
        # Closed trades: use profit_loss_dollars directly
        # Open trades: calculate unrealized P&L as (current_price - entry_price) * quantity
        cur.execute("""
            SELECT COALESCE(at.profit_loss_dollars,
                           CASE WHEN at.status != 'closed'
                                THEN (COALESCE(ap.current_price, at.entry_price) - at.entry_price) * at.entry_quantity
                                ELSE NULL END) as profit_loss_dollars,
                   COALESCE(at.profit_loss_pct,
                           CASE WHEN at.status != 'closed'
                                THEN ((COALESCE(ap.current_price, at.entry_price) - at.entry_price) / at.entry_price * 100)
                                ELSE NULL END) as profit_loss_pct,
                   at.exit_r_multiple,
                   (COALESCE(at.exit_date, CURRENT_DATE) - at.trade_date) as holding_days
            FROM algo_trades at
            LEFT JOIN algo_positions ap ON at.trade_id = ANY(ap.trade_ids_arr)
            WHERE (at.status = 'closed' AND at.exit_date IS NOT NULL)
               OR (at.status IN ('open', 'filled', 'partially_filled', 'active') AND ap.current_price IS NOT NULL)
            ORDER BY COALESCE(at.exit_date, CURRENT_DATE) DESC LIMIT 10000
        """)
        trades = cur.fetchall()

        if not trades:
            # No trades: raise instead of inserting artificial defaults
            msg = f"No trades (closed or open with current price) for {metric_date} — cannot compute performance metrics"
            logger.warning(msg)
            raise ValueError(msg)

        # Extract metrics from trades (filter out None values for open positions lacking realized P&L)
        pnl_dollars = [float(t["profit_loss_dollars"]) for t in trades if t["profit_loss_dollars"] is not None]
        pnl_pcts = [float(t["profit_loss_pct"]) for t in trades if t["profit_loss_pct"] is not None]
        [float(t["exit_r_multiple"]) for t in trades if t["exit_r_multiple"] is not None]
        holding_days_list = [float(t["holding_days"]) for t in trades if t["holding_days"]]

        # Basic counts
        total_trades: int = len(pnl_dollars)
        winning: int = sum(1 for p in pnl_dollars if p > 0)
        losing: int = sum(1 for p in pnl_dollars if p < 0)
        breakeven: int = sum(1 for p in pnl_dollars if p == 0)

        # Win rate
        decisive: int = winning + losing
        if decisive == 0:
            raise ValueError("Cannot calculate performance metrics — no trades in period")
        win_rate: float = winning / decisive * 100

        # P&L metrics
        wins_sum: float = sum(p for p in pnl_dollars if p > 0)
        losses_sum: float = abs(sum(p for p in pnl_dollars if p < 0))
        if losses_sum == 0:
            profit_factor: float = wins_sum if wins_sum > 0 else 1.0  # No losses = perfect when there are wins
        else:
            profit_factor = wins_sum / losses_sum
        total_pnl_dollars: float = sum(pnl_dollars)
        total_pnl_pct: float = sum(pnl_pcts)

        metrics["total_trades"] = total_trades
        metrics["winning_trades"] = winning
        metrics["losing_trades"] = losing
        metrics["breakeven_trades"] = breakeven
        metrics["win_rate_pct"] = round(win_rate, 2)
        metrics["profit_factor"] = round(profit_factor, 2)
        metrics["total_pnl_dollars"] = round(total_pnl_dollars, 2)
        metrics["total_pnl_pct"] = round(total_pnl_pct, 2)

        # Trade statistics
        if pnl_pcts:
            metrics["avg_trade_pct"] = round(sum(pnl_pcts) / len(pnl_pcts), 2)
            metrics["best_trade_pct"] = round(max(pnl_pcts), 2)
            metrics["worst_trade_pct"] = round(min(pnl_pcts), 2)
            win_pcts = [p for p in pnl_pcts if p > 0]
            loss_pcts = [p for p in pnl_pcts if p < 0]
            metrics["avg_win_pct"] = round(sum(win_pcts) / len(win_pcts), 2) if win_pcts else 0.0
            metrics["avg_loss_pct"] = round(sum(loss_pcts) / len(loss_pcts), 2) if loss_pcts else 0.0
        else:
            metrics["avg_trade_pct"] = 0.0
            metrics["best_trade_pct"] = 0.0
            metrics["worst_trade_pct"] = 0.0
            metrics["avg_win_pct"] = 0.0
            metrics["avg_loss_pct"] = 0.0

        metrics["avg_holding_days"] = (
            round(sum(holding_days_list) / len(holding_days_list), 1) if holding_days_list else 0.0
        )

        # Streak metrics
        best_win_streak, worst_loss_streak = _compute_streaks(pnl_dollars)
        metrics["best_win_streak"] = best_win_streak
        metrics["worst_loss_streak"] = worst_loss_streak

        # Advanced metrics from portfolio snapshots
        sharpe, sortino, max_dd, cagr, calmar = _compute_advanced_metrics(cur, metric_date)
        metrics["sharpe_ratio"] = round(sharpe, 4) if sharpe is not None else None
        metrics["sortino_ratio"] = round(sortino, 4) if sortino is not None else None
        metrics["max_drawdown_pct"] = round(max_dd * 100, 2) if max_dd is not None else None  # Convert to percentage
        metrics["cagr_pct"] = round(cagr * 100, 4)  # Convert to percentage
        metrics["calmar_ratio"] = round(calmar, 4) if calmar is not None else None

        # Insert or update
        _insert_performance_metrics(cur, metric_date, metrics)

        logger.info(
            f"Performance metrics computed for {metric_date}: "
            f"{total_trades} trades, {winning} wins, {losing} losses, "
            f"sharpe={metrics['sharpe_ratio']}, max_dd={metrics['max_drawdown_pct']}%"
        )

        return metrics

    except Exception as e:
        logger.error(f"Failed to compute performance metrics: {e}", exc_info=True)
        raise


def _compute_advanced_metrics(
    cur: Any, metric_date: date
) -> tuple[float | None, float | None, float, float, float | None]:
    """Compute Sharpe, Sortino, max drawdown, CAGR, and Calmar ratios using MetricsCalculator."""
    try:
        # Fetch all portfolio snapshots
        cur.execute("""
            SELECT snapshot_date, total_portfolio_value
            FROM algo_portfolio_snapshots
            ORDER BY snapshot_date ASC
        """)
        snapshots = cur.fetchall()

        if len(snapshots) < 2:
            raise ValueError(
                f"Insufficient portfolio snapshots for metrics calculation: {len(snapshots)} snapshot(s) found, "
                "need at least 2 to compute daily returns"
            )

        vals = [float(s["total_portfolio_value"]) for s in snapshots]
        dates = [s["snapshot_date"] for s in snapshots]

        # Calculate daily returns
        returns = []
        for i in range(1, len(vals)):
            if vals[i - 1] != 0:
                ret = (vals[i] - vals[i - 1]) / vals[i - 1]
                returns.append(ret)

        # Validate return scale: returns should be decimal (0.05 = 5%), not percentage (5.0 = 5%)
        if returns and max(abs(r) for r in returns) > 1:
            raise ValueError(
                f"Return scale error: detected returns > 100% (max={max(abs(r) for r in returns):.2f}). "
                "Returns should be decimal scale (0.05 = 5%), not percentage scale (5.0 = 5%). "
                "Data quality issue in portfolio snapshots — check snapshot calculation."
            )

        if not returns:
            raise ValueError(
                f"Insufficient returns data for metrics calculation: all {len(vals)} snapshots "
                "have zero or negative previous values; cannot compute daily returns"
            )

        # Calculate metrics with explicit error handling — fail-secure, no silent fallbacks
        try:
            sharpe = MetricsCalculator.calculate_sharpe_ratio(returns)
        except ValueError as e:
            logger.error(f"Sharpe ratio calculation failed: {e}")
            raise

        try:
            sortino = MetricsCalculator.calculate_sortino_ratio(returns)
        except ValueError as e:
            logger.error(f"Sortino ratio calculation failed: {e}")
            raise

        try:
            max_drawdown = MetricsCalculator.calculate_max_drawdown(vals)
        except ValueError as e:
            logger.error(f"Max drawdown calculation failed: {e}")
            raise

        try:
            calmar = MetricsCalculator.calculate_calmar_ratio(vals)
        except ValueError as e:
            logger.error(f"Calmar ratio calculation failed: {e}")
            raise

        # CAGR calculation (not in MetricsCalculator, so keep custom implementation)
        start_val = vals[0]
        end_val = vals[-1]
        n_days = (dates[-1] - dates[0]).days if len(dates) > 1 else 0
        cagr = 0.0
        if n_days > 0 and start_val > 0 and end_val > 0:
            cagr = (end_val / start_val) ** (365.25 / n_days) - 1

        if max_drawdown is None:
            raise ValueError("Cannot calculate max drawdown — no price data available")
        max_dd_pct = max_drawdown / 100.0
        return sharpe, sortino, max_dd_pct, cagr, calmar

    except Exception as e:
        raise RuntimeError(
            f"[PERFORMANCE_METRICS] Failed to compute metrics: {e}. Cannot report zeros—requires authoritative data."
        ) from e


def _compute_streaks(pnl_dollars: list[float]) -> tuple[int, int]:
    """Compute best win streak and worst loss streak."""
    best_win_streak = 0
    worst_loss_streak = 0

    if not pnl_dollars:
        return best_win_streak, worst_loss_streak

    current_streak = 0
    best_w = 0
    best_l = 0

    for pnl in reversed(pnl_dollars):
        if pnl > 0:
            current_streak = max(0, current_streak) + 1
        elif pnl < 0:
            current_streak = min(0, current_streak) - 1
        best_w = max(best_w, current_streak)
        best_l = min(best_l, current_streak)

    best_win_streak = best_w
    worst_loss_streak = abs(best_l)

    return best_win_streak, worst_loss_streak


def _insert_default_metrics(cur: Any, metric_date: date) -> None:
    """Insert default metrics when there are no trades."""
    cur.execute(
        """
        INSERT INTO algo_performance_metrics (
            metric_date, total_trades, winning_trades, losing_trades, breakeven_trades,
            win_rate_pct, profit_factor, total_pnl_dollars, total_pnl_pct,
            avg_trade_pct, best_trade_pct, worst_trade_pct, avg_win_pct, avg_loss_pct,
            avg_holding_days, sharpe_ratio, sortino_ratio, max_drawdown_pct, calmar_ratio,
            cagr_pct, best_win_streak, worst_loss_streak
        ) VALUES (%s, 0, 0, 0, 0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0,
                  0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0, 0)
        ON CONFLICT (metric_date) DO NOTHING
    """,
        (metric_date,),
    )


def _insert_performance_metrics(cur: Any, metric_date: date, metrics: dict[str, Any]) -> None:
    """Insert or update performance metrics in database."""
    try:
        cur.execute(
            """
            INSERT INTO algo_performance_metrics (
                metric_date, total_trades, winning_trades, losing_trades, breakeven_trades,
                win_rate_pct, profit_factor, total_pnl_dollars, total_pnl_pct,
                avg_trade_pct, best_trade_pct, worst_trade_pct, avg_win_pct, avg_loss_pct,
                avg_holding_days, sharpe_ratio, sortino_ratio, max_drawdown_pct, calmar_ratio,
                cagr_pct, best_win_streak, worst_loss_streak
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (metric_date) DO UPDATE SET
                total_trades = EXCLUDED.total_trades,
                winning_trades = EXCLUDED.winning_trades,
                losing_trades = EXCLUDED.losing_trades,
                breakeven_trades = EXCLUDED.breakeven_trades,
                win_rate_pct = EXCLUDED.win_rate_pct,
                profit_factor = EXCLUDED.profit_factor,
                total_pnl_dollars = EXCLUDED.total_pnl_dollars,
                total_pnl_pct = EXCLUDED.total_pnl_pct,
                avg_trade_pct = EXCLUDED.avg_trade_pct,
                best_trade_pct = EXCLUDED.best_trade_pct,
                worst_trade_pct = EXCLUDED.worst_trade_pct,
                avg_win_pct = EXCLUDED.avg_win_pct,
                avg_loss_pct = EXCLUDED.avg_loss_pct,
                avg_holding_days = EXCLUDED.avg_holding_days,
                sharpe_ratio = EXCLUDED.sharpe_ratio,
                sortino_ratio = EXCLUDED.sortino_ratio,
                max_drawdown_pct = EXCLUDED.max_drawdown_pct,
                calmar_ratio = EXCLUDED.calmar_ratio,
                cagr_pct = EXCLUDED.cagr_pct,
                best_win_streak = EXCLUDED.best_win_streak,
                worst_loss_streak = EXCLUDED.worst_loss_streak,
                updated_at = NOW()
        """,
            (
                metric_date,
                metrics["total_trades"],
                metrics["winning_trades"],
                metrics["losing_trades"],
                metrics["breakeven_trades"],
                metrics["win_rate_pct"],
                metrics["profit_factor"],
                metrics["total_pnl_dollars"],
                metrics["total_pnl_pct"],
                metrics["avg_trade_pct"],
                metrics["best_trade_pct"],
                metrics["worst_trade_pct"],
                metrics["avg_win_pct"],
                metrics["avg_loss_pct"],
                metrics["avg_holding_days"],
                metrics["sharpe_ratio"],
                metrics["sortino_ratio"],
                metrics["max_drawdown_pct"],
                metrics["calmar_ratio"],
                metrics["cagr_pct"],
                metrics["best_win_streak"],
                metrics["worst_loss_streak"],
            ),
        )
    except Exception as e:
        logger.error(f"Failed to insert performance metrics: {e}", exc_info=True)
        raise


def main() -> None:
    """Main entry point for the loader."""
    try:
        with DatabaseContext("write", cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            compute_performance_metrics(cur)
            logger.info("Performance metrics loader completed successfully")
    except (psycopg2.DatabaseError, psycopg2.OperationalError) as e:
        logger.error(f"Performance metrics loader failed: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    main()
