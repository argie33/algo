#!/usr/bin/env python3
"""Algo Performance Daily Loader - Rolling sharpe, sortino, calmar, win rate, expectancy.

Runs multiple times per day (e.g., hourly 10:00 AM - 5:00 PM ET) to keep metrics current.
Calculates all-time rolling metrics for the current trading day based on:
  - algo_trades (all closed + open trades for accurate win rate)
  - algo_portfolio_snapshots (for equity curve, returns, drawdown)

Metrics are updated-at timestamps so dashboard knows freshness.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import logging
import statistics
from datetime import date, datetime, timezone
from typing import Optional, List
from zoneinfo import ZoneInfo

from utils.optimal_loader import OptimalLoader
from utils.database_context import DatabaseContext

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
        """Compute performance metrics from all closed trades and equity curve.

        Metrics:
        - rolling_sharpe_252d: (252-day annualized sharpe from daily returns)
        - rolling_sortino_252d: (downside risk only)
        - calmar_ratio: (cumulative return / max drawdown)
        - win_rate_50t: (last 50 closed trades)
        - avg_win_r_50t, avg_loss_r_50t: (average R-multiple)
        - expectancy: (expected value per trade)
        - max_drawdown_pct: (peak-to-trough from snapshots)
        """
        try:
            now_et = datetime.now(ET)
            report_date = now_et.date()

            with DatabaseContext('read') as cur:
                # 1. Fetch all closed trades for win rate / expectancy
                cur.execute("""
                    SELECT
                        COUNT(*) as total_trades,
                        COUNT(*) FILTER (WHERE profit_loss_dollars > 0) as wins,
                        COUNT(*) FILTER (WHERE profit_loss_dollars < 0) as losses,
                        AVG(exit_r_multiple) as avg_r_all,
                        AVG(exit_r_multiple) FILTER (WHERE profit_loss_dollars > 0) as avg_win_r,
                        AVG(exit_r_multiple) FILTER (WHERE profit_loss_dollars < 0) as avg_loss_r
                    FROM algo_trades
                    WHERE status = 'closed' AND exit_date IS NOT NULL
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
        """Calculate all performance metrics."""

        # Win rate from all trades
        total_trades_val = trade_stats.get('total_trades')
        wins_val = trade_stats.get('wins')
        losses_val = trade_stats.get('losses')
        total_trades = int(total_trades_val) if total_trades_val is not None else None
        wins = int(wins_val) if wins_val is not None else None
        losses = int(losses_val) if losses_val is not None else None
        win_rate_all = round(wins / total_trades * 100, 2) if total_trades is not None and total_trades > 0 else None

        # Fetch dollar amounts for profit factor and average win/loss (CRITICAL ISSUE 2 FIX)
        # ISSUE 36 FIX: Count breakeven trades explicitly to detect overstatement of profit factor
        avg_win_dollars = None
        avg_loss_dollars = None
        profit_factor = None
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
                    WHERE status = 'closed' AND exit_date IS NOT NULL
                """)
                row = cur.fetchone() or {}
                avg_win_dollars = float(row.get('avg_win_dollars')) if row.get('avg_win_dollars') is not None else None
                avg_loss_dollars = float(row.get('avg_loss_dollars')) if row.get('avg_loss_dollars') is not None else None

                # CRITICAL ISSUE 2 FIX: Profit factor = total wins / total losses (avoid None for edge cases)
                # ISSUE 36 FIX: Note that breakeven trades are excluded from both numerator and denominator
                # If breakeven_count > 5% of total, profit_factor can overstate actual profitability
                total_wins = float(row.get('total_wins')) if row.get('total_wins') is not None else 0.0
                total_losses = float(row.get('total_losses')) if row.get('total_losses') is not None else 0.0
                breakeven_val = row.get('breakeven_count')
                breakeven_count = int(breakeven_val) if breakeven_val is not None else None
                if total_losses > 1e-6:  # Avoid division by zero
                    profit_factor = round(total_wins / total_losses, 3)
                    if total_trades > 0 and breakeven_count > total_trades * 0.05:
                        logger.warning(f"Profit factor ({profit_factor:.3f}) may be overstated: {breakeven_count} breakeven trades ({breakeven_count/total_trades*100:.1f}%)")
                elif total_losses == 0 and total_wins > 0:
                    profit_factor = float('inf')  # Perfect record (only wins, no losses)
                # else: profit_factor stays None (no trades or undefined)
        except Exception as e:
            logger.warning(f"Failed to fetch dollar amounts for profit factor: {e}")

        # Expectancy: E[profit] = win_rate * avg_win - (1 - win_rate) * avg_loss
        avg_win_r = trade_stats.get('avg_win_r')
        avg_loss_r = trade_stats.get('avg_loss_r')
        expectancy = None
        if win_rate_all is not None and avg_win_r is not None and avg_loss_r is not None:
            try:
                wr_dec = win_rate_all / 100
                expectancy = round(wr_dec * float(avg_win_r) - (1 - wr_dec) * abs(float(avg_loss_r)), 3)
            except (TypeError, ValueError):
                pass

        # 50-trade metrics
        win_rate_50t = None
        avg_win_r_50t = None
        avg_loss_r_50t = None
        if len(recent_trades) > 0:
            wins_50 = sum(1 for t in recent_trades if t.get('profit_loss_dollars') and float(t['profit_loss_dollars']) > 0)
            wr_50 = wins_50 / len(recent_trades) * 100
            win_rate_50t = round(wr_50, 2)

            wins_50_r = [float(t['exit_r_multiple']) for t in recent_trades
                        if t.get('exit_r_multiple') and float(t['profit_loss_dollars']) > 0]
            losses_50_r = [float(t['exit_r_multiple']) for t in recent_trades
                          if t.get('exit_r_multiple') and float(t['profit_loss_dollars']) < 0]

            if wins_50_r:
                avg_win_r_50t = round(statistics.mean(wins_50_r), 3)
            if losses_50_r:
                avg_loss_r_50t = round(statistics.mean(losses_50_r), 3)

        # Equity curve metrics
        equity_vals = [float(s['total_portfolio_value']) for s in snapshots
                      if s.get('total_portfolio_value') is not None]
        returns = [float(s['daily_return_pct']) / 100 for s in snapshots
                  if s.get('daily_return_pct') is not None]

        # Max drawdown
        max_drawdown_pct = None
        if len(equity_vals) >= 2:
            peak = 0
            dd = 0
            for v in equity_vals:
                if v > peak:
                    peak = v
                if peak > 0:
                    dd = max(dd, (peak - v) / peak * 100)
            max_drawdown_pct = round(dd, 2)

        # Sharpe (252-day annualized)
        rolling_sharpe_252d = None
        if len(returns) > 5:
            try:
                mean_ret = statistics.mean(returns)
                std_ret = statistics.stdev(returns) if len(returns) > 1 else 0
                if std_ret > 0:
                    rolling_sharpe_252d = round(mean_ret / std_ret * (252 ** 0.5), 3)
            except (ValueError, ZeroDivisionError):
                pass

        # Sortino (only downside volatility)
        rolling_sortino_252d = None
        if len(returns) > 5:
            try:
                mean_ret = statistics.mean(returns)
                downside_rets = [r for r in returns if r < 0]
                if downside_rets:
                    downside_std = statistics.stdev(downside_rets) if len(downside_rets) > 1 else 0
                    if downside_std > 0:
                        rolling_sortino_252d = round(mean_ret / downside_std * (252 ** 0.5), 3)
            except (ValueError, ZeroDivisionError):
                pass

        # Calmar (return / max drawdown)
        calmar_ratio = None
        if max_drawdown_pct and max_drawdown_pct > 0 and len(returns) > 0:
            try:
                cumulative_return = 1.0
                for r in returns:
                    cumulative_return *= (1 + r)
                total_return = (cumulative_return - 1) * 100  # Convert to percentage
                calmar_ratio = round(total_return / max_drawdown_pct, 3) if max_drawdown_pct > 0 else None
            except (ValueError, ZeroDivisionError):
                pass

        # Extract avg_r_all from trade_stats (already computed in fetch_global)
        avg_r_all = None
        if trade_stats.get('avg_r_all') is not None:
            try:
                avg_r_all = round(float(trade_stats.get('avg_r_all')), 3)
            except (ValueError, TypeError):
                pass

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
