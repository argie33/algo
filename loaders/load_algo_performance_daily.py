#!/usr/bin/env python3
"""Algo Performance Daily Loader - Rolling sharpe, sortino, calmar, win rate, expectancy.

Runs multiple times per day (e.g., hourly 10:00 AM - 5:00 PM ET) to keep metrics current.
Calculates all-time rolling metrics for the current trading day based on:
  - algo_trades (all closed + open trades for accurate win rate)
  - algo_portfolio_snapshots (for equity curve, returns, drawdown)

CRITICAL: Uses central MetricsCalculator for all calculations to ensure consistency
across loaders, API, and dashboard. Never recalculate metrics locally.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
from datetime import date, datetime, timezone
from typing import Optional, List
from zoneinfo import ZoneInfo

from utils.optimal_loader import OptimalLoader
from utils.database_context import DatabaseContext
from utils.metrics_calculator import MetricsCalculator

logger = logging.getLogger(__name__)
ET = ZoneInfo("America/New_York")


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
                # Open trades count as potential wins if unrealized P&L > 0, losses if < 0
                cur.execute("""
                    SELECT
                        COUNT(*) as total_trades,
                        COUNT(*) FILTER (WHERE profit_loss_dollars > 0) as wins,
                        COUNT(*) FILTER (WHERE profit_loss_dollars < 0) as losses,
                        AVG(exit_r_multiple) as avg_r_all,
                        AVG(exit_r_multiple) FILTER (WHERE profit_loss_dollars > 0) as avg_win_r,
                        AVG(exit_r_multiple) FILTER (WHERE profit_loss_dollars < 0) as avg_loss_r
                    FROM algo_trades
                    WHERE (status = 'closed' AND exit_date IS NOT NULL)
                       OR (status != 'closed' AND profit_loss_dollars IS NOT NULL)
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
        try:
            with DatabaseContext('read') as cur:
                cur.execute("""
                    SELECT
                        AVG(profit_loss_dollars) FILTER (WHERE profit_loss_dollars > 0) as avg_win_dollars,
                        AVG(ABS(profit_loss_dollars)) FILTER (WHERE profit_loss_dollars < 0) as avg_loss_dollars,
                        SUM(profit_loss_dollars) FILTER (WHERE profit_loss_dollars > 0) as total_wins,
                        SUM(ABS(profit_loss_dollars)) FILTER (WHERE profit_loss_dollars < 0) as total_losses,
                        COUNT(*) FILTER (WHERE profit_loss_dollars = 0) as breakeven_count
                    FROM algo_trades
                    WHERE (status = 'closed' AND exit_date IS NOT NULL)
                       OR (status != 'closed' AND profit_loss_dollars IS NOT NULL)
                """)
                row = cur.fetchone() or {}
                avg_win_dollars = float(row.get('avg_win_dollars')) if row.get('avg_win_dollars') is not None else None
                avg_loss_dollars = float(row.get('avg_loss_dollars')) if row.get('avg_loss_dollars') is not None else None

                total_wins = float(row.get('total_wins')) if row.get('total_wins') is not None else 0.0
                total_losses = float(row.get('total_losses')) if row.get('total_losses') is not None else 0.0
                breakeven_val = row.get('breakeven_count')
                breakeven_count = int(breakeven_val) if breakeven_val is not None else None

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

        # 50-trade metrics
        win_rate_50t = None
        avg_win_r_50t = None
        avg_loss_r_50t = None
        if len(recent_trades) > 0:
            wins_50 = sum(1 for t in recent_trades if t.get('profit_loss_dollars') and float(t['profit_loss_dollars']) > 0)
            win_rate_50t = MetricsCalculator.calculate_win_rate(
                len(recent_trades), wins_50, len(recent_trades) - wins_50
            )

            wins_50_r = [float(t['exit_r_multiple']) for t in recent_trades
                        if t.get('exit_r_multiple') and float(t['profit_loss_dollars']) > 0]
            losses_50_r = [float(t['exit_r_multiple']) for t in recent_trades
                          if t.get('exit_r_multiple') and float(t['profit_loss_dollars']) < 0]

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

        # Extract avg_r_all from trade_stats (already computed in fetch_global)
        avg_r_all = None
        if trade_stats.get('avg_r_all') is not None:
            avg_r_all = MetricsCalculator.calculate_avg_r_multiple([float(trade_stats.get('avg_r_all'))])

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
            'avg_r': avg_r_all,
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
