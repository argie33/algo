#!/usr/bin/env python3
"""Algo Performance Daily Loader - Rolling sharpe, sortino, calmar, win rate, expectancy.

Runs multiple times per day (e.g., hourly 10:00 AM - 5:00 PM ET) to keep metrics current.
Calculates all-time rolling metrics for the current trading day based on:
  - algo_trades (all closed + open trades for accurate win rate)
  - algo_portfolio_snapshots (for equity curve, returns, drawdown)

CRITICAL: Uses central MetricsCalculator for all calculations to ensure consistency
across loaders, API, and dashboard. Never recalculate metrics locally.
"""
from loaders.loader_helper import setup_imports
setup_imports()

import sys
import logging
from datetime import date, datetime, timezone
from typing import Optional, List

from utils.optimal_loader import OptimalLoader
from utils.timezone_utils import EASTERN_TZ
from utils.database_context import DatabaseContext
from utils.metrics_calculator import MetricsCalculator

logger = logging.getLogger(__name__)
ET = EASTERN_TZ

class AlgoPerformanceDailyLoader(OptimalLoader):
    """Compute rolling performance metrics hourly during market hours."""

    table_name = "algo_performance_daily"
    primary_key = ("report_date",)
    watermark_field = "report_date"

    # Allow multiple updates per day (not just once)
    allow_multiple_updates_per_day = True

    def fetch_global(self, since: Optional[date]) -> Optional[List[dict]]:
        """Compute performance metrics from all closed + open trades and equity curve.

        H15 FIX: Win rate now includes open trades (based on unrealized P&L)
        H16 FIX: Win rate accounts for unrealized risk on open positions

        Metrics:
        - rolling_sharpe_252d: (252-day annualized sharpe from daily returns, includes unrealized gains/losses via snapshots)
        - rolling_sortino_252d: (downside risk only)
        - calmar_ratio: (cumulative return / max drawdown)
        - win_rate_all: (all closed trades + open trades by unrealized P&L status)
        - win_rate_50t: (last 50 closed trades only, for consistency with historical records)
        - avg_win_r_50t, avg_loss_r_50t: (average R-multiple from last 50)
        - expectancy: (expected value per trade)
        - max_drawdown_pct: (peak-to-trough from snapshots)
        """
        try:
            now_et = datetime.now(ET)
            report_date = now_et.date()

            with DatabaseContext('read') as cur:
                # 1. Fetch all closed trades + open trades for comprehensive win rate (H15, H16 FIX)
                # Closed trades: use profit_loss_dollars (already calculated at exit)
                # Open trades: calculate unrealized P&L as (current_price - entry_price) * quantity
                cur.execute("""
                    SELECT
                        COUNT(*) as total_trades,
                        COUNT(*) FILTER (WHERE pnl > 0) as wins,
                        COUNT(*) FILTER (WHERE pnl < 0) as losses,
                        AVG(at.exit_r_multiple) as avg_r_all,
                        AVG(at.exit_r_multiple) FILTER (WHERE pnl > 0) as avg_win_r,
                        AVG(at.exit_r_multiple) FILTER (WHERE pnl < 0) as avg_loss_r
                    FROM (
                        SELECT
                            at.exit_r_multiple,
                            COALESCE(at.profit_loss_dollars,
                                    CASE WHEN at.status != 'closed'
                                         THEN (ap.current_price - at.entry_price) * at.entry_quantity
                                         ELSE NULL END) as pnl
                        FROM algo_trades at
                        LEFT JOIN algo_positions ap ON at.trade_id = ANY(ap.trade_ids_arr)
                        WHERE (at.status = 'closed' AND at.exit_date IS NOT NULL)
                           OR (at.status IN ('open', 'filled', 'partially_filled', 'active') AND ap.current_price IS NOT NULL)
                    ) t
                """)
                trade_stats = cur.fetchone() or {}

                # Recent 50 trades for short-term metrics
                cur.execute("""
                    SELECT exit_r_multiple, profit_loss_dollars
                    FROM algo_trades
                    WHERE status = 'closed' AND exit_date IS NOT NULL
                    ORDER BY exit_date DESC LIMIT 50
                """)
                recent_trades = cur.fetchall() or []

                # 2. Fetch portfolio snapshots for equity curve, drawdown, sharpe
                cur.execute("""
                    SELECT snapshot_date, total_portfolio_value, daily_return_pct
                    FROM algo_portfolio_snapshots
                    ORDER BY snapshot_date ASC
                """)
                snapshots = cur.fetchall() or []

            if not snapshots:
                logger.warning(f"No portfolio snapshots available for {report_date}")
                return None

            result = self._calculate_metrics(report_date, trade_stats, recent_trades, snapshots)
            return [result] if result else None

        except Exception as e:
            logger.error(f"Failed to compute performance metrics: {e}")
            return None

    def _calculate_metrics(self, report_date: date, trade_stats: dict,
                          recent_trades: list, snapshots: list) -> dict:
        """Calculate all performance metrics using central MetricsCalculator.

        Uses MetricsCalculator for all calculations to ensure consistency
        across loaders, API, and dashboard. No local recalculations.

        Computes all metrics pre-computed for API layer (Phase 1 fix):
        - Streaks (current, best_win, worst_loss)
        - Total P&L and gross amounts
        - Win/loss percentages
        - Average hold days
        """

        # Extract trade counts
        total_trades_val = trade_stats.get('total_trades')
        wins_val = trade_stats.get('wins')
        losses_val = trade_stats.get('losses')
        total_trades = int(total_trades_val) if total_trades_val is not None else None
        wins = int(wins_val) if wins_val is not None else None
        losses = int(losses_val) if losses_val is not None else None

        # Win rate (using central calculator)
        win_rate_all = MetricsCalculator.calculate_win_rate(
            total_trades, wins, losses
        )

        # Fetch dollar amounts for profit factor and average win/loss
        avg_win_dollars = None
        avg_loss_dollars = None
        profit_factor = None
        breakeven_count = None
        total_pnl = None
        gross_wins = None
        gross_losses = None
        avg_win_pct = None
        avg_loss_pct = None
        avg_hold_days = None
        biggest_win = None
        biggest_loss = None
        best_trade_r = None
        worst_trade_r = None
        try:
            with DatabaseContext('read') as cur:
                cur.execute("""
                    SELECT
                        AVG(pnl) FILTER (WHERE pnl > 0) as avg_win_dollars,
                        AVG(ABS(pnl)) FILTER (WHERE pnl < 0) as avg_loss_dollars,
                        SUM(pnl) FILTER (WHERE pnl > 0) as total_wins,
                        SUM(ABS(pnl)) FILTER (WHERE pnl < 0) as total_losses,
                        SUM(pnl) as total_pnl,
                        COUNT(*) FILTER (WHERE pnl = 0) as breakeven_count,
                        AVG(pnl_pct) FILTER (WHERE pnl > 0) as avg_win_pct,
                        AVG(pnl_pct) FILTER (WHERE pnl < 0) as avg_loss_pct,
                        AVG(at.trade_duration_days) as avg_hold_days,
                        MAX(pnl) as biggest_win,
                        MIN(pnl) as biggest_loss,
                        MAX(at.exit_r_multiple) as best_trade_r,
                        MIN(at.exit_r_multiple) as worst_trade_r
                    FROM (
                        SELECT
                            at.exit_r_multiple,
                            at.trade_duration_days,
                            COALESCE(at.profit_loss_dollars,
                                    CASE WHEN at.status != 'closed'
                                         THEN (ap.current_price - at.entry_price) * at.entry_quantity
                                         ELSE NULL END) as pnl,
                            COALESCE(at.profit_loss_pct,
                                    CASE WHEN at.status != 'closed'
                                         THEN ((ap.current_price - at.entry_price) / at.entry_price * 100)
                                         ELSE NULL END) as pnl_pct
                        FROM algo_trades at
                        LEFT JOIN algo_positions ap ON at.trade_id = ANY(ap.trade_ids_arr)
                        WHERE (at.status = 'closed' AND at.exit_date IS NOT NULL)
                           OR (at.status IN ('open', 'filled', 'partially_filled', 'active') AND ap.current_price IS NOT NULL)
                    ) t
                """)
                row = cur.fetchone() or {}
                avg_win_dollars = float(row.get('avg_win_dollars')) if row.get('avg_win_dollars') is not None else None
                avg_loss_dollars = float(row.get('avg_loss_dollars')) if row.get('avg_loss_dollars') is not None else None

                total_wins = float(row.get('total_wins')) if row.get('total_wins') is not None else 0.0
                total_losses = float(row.get('total_losses')) if row.get('total_losses') is not None else 0.0
                total_pnl = float(row.get('total_pnl')) if row.get('total_pnl') is not None else None
                gross_wins = float(row.get('total_wins')) if row.get('total_wins') is not None else 0.0
                gross_losses = float(row.get('total_losses')) if row.get('total_losses') is not None else 0.0

                breakeven_val = row.get('breakeven_count')
                breakeven_count = int(breakeven_val) if breakeven_val is not None else None

                avg_win_pct = float(row.get('avg_win_pct')) if row.get('avg_win_pct') is not None else None
                avg_loss_pct = float(row.get('avg_loss_pct')) if row.get('avg_loss_pct') is not None else None
                avg_hold_days = float(row.get('avg_hold_days')) if row.get('avg_hold_days') is not None else None
                biggest_win = float(row.get('biggest_win')) if row.get('biggest_win') is not None else None
                biggest_loss = float(row.get('biggest_loss')) if row.get('biggest_loss') is not None else None
                best_trade_r = float(row.get('best_trade_r')) if row.get('best_trade_r') is not None else None
                worst_trade_r = float(row.get('worst_trade_r')) if row.get('worst_trade_r') is not None else None

                # Use central calculator for profit factor
                profit_factor = MetricsCalculator.calculate_profit_factor(
                    total_wins, total_losses
                )
                if profit_factor and total_trades and breakeven_count and breakeven_count > total_trades * 0.05:
                    logger.warning(f"Profit factor ({profit_factor:.3f}) may be overstated: {breakeven_count} breakeven trades ({breakeven_count/total_trades*100:.1f}%)")
        except Exception as e:
            logger.warning(f"Failed to fetch dollar amounts for profit factor: {e}")

        # Expectancy using central calculator
        avg_win_r = trade_stats.get('avg_win_r')
        avg_loss_r = trade_stats.get('avg_loss_r')
        expectancy = MetricsCalculator.calculate_expectancy(
            win_rate_all, avg_win_r, avg_loss_r
        )

        # PHASE 1 FIX: Compute streaks (current, best_win, worst_loss)
        current_streak = 0
        best_win_streak = 0
        worst_loss_streak = 0
        try:
            with DatabaseContext('read') as cur:
                # Fetch all trades ordered by date for streak analysis
                cur.execute("""
                    SELECT profit_loss_dollars FROM algo_trades
                    WHERE status = 'closed' AND exit_date IS NOT NULL
                    ORDER BY exit_date ASC
                """)
                all_trades = cur.fetchall() or []

                # Calculate streaks (skip trades with missing P&L — don't mask with fallback to 0)
                if all_trades:
                    temp_win = 0
                    temp_loss = 0
                    for trade in all_trades:
                        pnl_val = trade.get('profit_loss_dollars')
                        if pnl_val is None:
                            logger.warning(f"Trade {trade.get('trade_id')} missing profit_loss_dollars, skipping from streak")
                            continue
                        pnl = float(pnl_val)
                        if pnl > 0:
                            temp_win += 1
                            temp_loss = 0
                            best_win_streak = max(best_win_streak, temp_win)
                            current_streak = temp_win
                        elif pnl < 0:
                            temp_loss += 1
                            temp_win = 0
                            worst_loss_streak = max(worst_loss_streak, temp_loss)
                            current_streak = -temp_loss
                        # Break-even trades don't change streak state (temp stays 0)
        except Exception as e:
            logger.warning(f"Failed to compute streaks: {e}")

        # 50-trade metrics (explicit None checks instead of fallbacks)
        win_rate_50t = None
        avg_win_r_50t = None
        avg_loss_r_50t = None
        if recent_trades:
            # Count wins/losses only for trades with non-null P&L
            valid_trades = [t for t in recent_trades if t.get('profit_loss_dollars') is not None]
            if valid_trades:
                pnl_vals = [float(t['profit_loss_dollars']) for t in valid_trades]
                wins_50 = sum(1 for p in pnl_vals if p > 0)
                losses_50 = sum(1 for p in pnl_vals if p < 0)
                win_rate_50t = MetricsCalculator.calculate_win_rate(
                    len(valid_trades), wins_50, losses_50
                )

                wins_50_r = [float(t['exit_r_multiple']) for t in valid_trades
                            if t.get('exit_r_multiple') is not None and float(t['profit_loss_dollars']) > 0]
                losses_50_r = [float(t['exit_r_multiple']) for t in valid_trades
                              if t.get('exit_r_multiple') is not None and float(t['profit_loss_dollars']) < 0]

                if wins_50_r:
                    avg_win_r_50t = MetricsCalculator.calculate_avg_r_multiple(wins_50_r)
                if losses_50_r:
                    avg_loss_r_50t = MetricsCalculator.calculate_avg_r_multiple(losses_50_r)

        # Equity curve metrics
        equity_vals = [float(s['total_portfolio_value']) for s in snapshots
                      if s.get('total_portfolio_value') is not None]
        returns = [float(s['daily_return_pct']) / 100 for s in snapshots
                  if s.get('daily_return_pct') is not None]

        # Max drawdown (using central calculator)
        max_drawdown_pct = MetricsCalculator.calculate_max_drawdown(equity_vals)

        # Sharpe (using central calculator)
        rolling_sharpe_252d = MetricsCalculator.calculate_sharpe_ratio(returns, min_observations=5)

        # Sortino (using central calculator)
        rolling_sortino_252d = MetricsCalculator.calculate_sortino_ratio(returns, min_observations=5)

        # Calmar (using central calculator)
        calmar_ratio = MetricsCalculator.calculate_calmar_ratio(equity_vals, min_observations=2)

        # Total return % from equity curve (from snapshots)
        total_return_pct = None
        if equity_vals and len(equity_vals) >= 2:
            start_val = equity_vals[0]
            end_val = equity_vals[-1]
            if start_val > 0:
                total_return_pct = ((end_val - start_val) / start_val) * 100

        return {
            'report_date': report_date,
            'rolling_sharpe_252d': rolling_sharpe_252d,
            'rolling_sortino_252d': rolling_sortino_252d,
            'calmar_ratio': calmar_ratio,
            'win_rate_50t': win_rate_50t,
            'avg_win_r_50t': avg_win_r_50t,
            'avg_loss_r_50t': avg_loss_r_50t,
            'expectancy': expectancy,
            'max_drawdown_pct': max_drawdown_pct,
            'total_trades': total_trades,
            'win_rate_all': win_rate_all,
            'num_wins': wins,
            'num_losses': losses,
            'profit_factor': profit_factor,
            'avg_win': avg_win_dollars,
            'avg_loss': avg_loss_dollars,
            'avg_r': avg_win_r,
            # PHASE 1 FIX: New fields to support API performance endpoint
            'current_win_streak': current_streak,
            'best_win_streak': best_win_streak,
            'worst_loss_streak': worst_loss_streak,
            'avg_win_pct': avg_win_pct,
            'avg_loss_pct': avg_loss_pct,
            'avg_loss_r': avg_loss_r,
            'total_pnl_dollars': total_pnl,
            'gross_win_dollars': gross_wins,
            'gross_loss_dollars': gross_losses,
            'total_return_pct': total_return_pct,
            'avg_hold_days': avg_hold_days,
            'portfolio_snapshots_count': len(snapshots),
            'biggest_win': biggest_win,
            'biggest_loss': biggest_loss,
            'best_trade_r': best_trade_r,
            'worst_trade_r': worst_trade_r,
            'updated_at': datetime.now(ET),
        }

def main():
    loader = AlgoPerformanceDailyLoader()
    result = loader.load_global()

    if result > 0:
        logger.info(f"SUCCESS: {result} performance metrics computed")
        return 0
    else:
        logger.warning(f"COMPLETED: No metrics computed (insufficient data)")
        return 0

if __name__ == "__main__":
    sys.exit(main())
