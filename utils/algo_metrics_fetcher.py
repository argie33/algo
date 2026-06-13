#!/usr/bin/env python3
"""Unified Metrics & Positions Fetcher — Single Source of Truth

This module consolidates ALL data fetching for:
- Performance metrics (win_rate, sharpe, max_drawdown, etc.)
- Position data (open positions, P&L, targets, stops)

Previously, performance metrics came through API (complex routing),
while positions came directly from DB (simple). This created inconsistency.

Now both use this unified interface to ensure:
1. Single code path for data retrieval
2. Consistent validation and error handling
3. Easy debugging (all logic in one place)
4. Dashboard and API use identical data sources
"""

import logging
import psycopg2
import psycopg2.extras
import math
from typing import Dict, List, Optional, Any
from datetime import datetime, date

logger = logging.getLogger(__name__)


class AlgoMetricsFetcher:
    """Unified fetcher for performance metrics and positions from database."""

    def __init__(self, cursor):
        """Initialize with database cursor.

        Args:
            cursor: psycopg2 cursor (DictCursor preferred for named access)
        """
        self.cursor = cursor

    @staticmethod
    def _mean(xs: List[float]) -> float:
        """Calculate mean of list."""
        return sum(xs) / len(xs) if xs else 0.0

    @staticmethod
    def _std(xs: List[float]) -> float:
        """Calculate sample standard deviation."""
        if len(xs) < 2:
            return 0.0
        m = AlgoMetricsFetcher._mean(xs)
        return math.sqrt(sum((x - m) ** 2 for x in xs) / len(xs))

    @staticmethod
    def _max_drawdown_pct(returns: List[float]) -> float:
        """Calculate maximum drawdown from returns list.

        Args:
            returns: List of daily returns as decimals (0.01 = +1%)

        Returns:
            Max drawdown as negative percentage (e.g., -0.15 for -15%)
        """
        cum, peak, max_dd = 1.0, 1.0, 0.0
        for r in returns:
            cum *= (1 + r)
            if cum > peak:
                peak = cum
            dd = (cum - peak) / peak
            if dd < max_dd:
                max_dd = dd
        return max_dd

    def fetch_performance_metrics(self) -> Dict[str, Any]:
        """Fetch all performance metrics from database.

        Returns comprehensive performance data including:
        - Trade statistics (wins, losses, win rate)
        - Profitability metrics (Sharpe, Sortino, max drawdown)
        - Streak analysis (current, best, worst)

        Returns:
            Dict with all performance metrics, or error dict if fetch fails
        """
        try:
            # Fetch closed trades for performance calculation
            self.cursor.execute("""
                SELECT trade_id, symbol, trade_date, exit_date, entry_price, exit_price,
                       entry_quantity, profit_loss_dollars, profit_loss_pct,
                       exit_r_multiple,
                       (COALESCE(exit_date, CURRENT_DATE) - trade_date) as holding_days
                FROM algo_trades
                WHERE exit_date IS NOT NULL
                ORDER BY exit_date DESC
                LIMIT 1000
            """)
            trades = [dict(row) for row in self.cursor.fetchall()]

            if not trades:
                logger.info("fetch_performance_metrics: No closed trades found")
                return self._empty_performance_response()

            # Extract P&L and R-multiple data
            pnl_dollars = [float(t.get('profit_loss_dollars') or 0) for t in trades]
            pnl_pcts = [float(t.get('profit_loss_pct') or 0) for t in trades]
            r_multiples = [float(t['exit_r_multiple']) for t in trades
                          if t.get('exit_r_multiple') is not None]
            holding_days = [float(t.get('holding_days') or 0) for t in trades
                           if t.get('holding_days')]

            # Count trade outcomes
            winning = sum(1 for p in pnl_dollars if p > 0)
            losing = sum(1 for p in pnl_dollars if p < 0)
            breakeven = sum(1 for p in pnl_dollars if p == 0)
            total = len(trades)

            # Win rate (excludes breakeven)
            win_loss_total = winning + losing
            win_rate_pct = (winning / win_loss_total * 100) if win_loss_total > 0 else 0.0

            # Profit factor
            wins_sum = sum(p for p in pnl_dollars if p > 0)
            losses_sum = abs(sum(p for p in pnl_dollars if p < 0))
            profit_factor = (wins_sum / losses_sum) if losses_sum > 0 else 0.0

            # Win/loss averages
            wins_pcts = [p for p in pnl_pcts if p > 0]
            losses_pcts = [p for p in pnl_pcts if p < 0]
            avg_win_pct = self._mean(wins_pcts) if wins_pcts else 0.0
            avg_loss_pct = self._mean(losses_pcts) if losses_pcts else 0.0

            # Sharpe & Sortino from portfolio snapshots
            sharpe_ratio, sortino_ratio, max_dd_pct = None, None, None
            snapshot_count = 0
            total_return_pct = None

            try:
                self.cursor.execute("""
                    SELECT snapshot_date, total_portfolio_value
                    FROM algo_portfolio_snapshots
                    ORDER BY snapshot_date ASC
                """)
                snapshots = [dict(row) for row in self.cursor.fetchall()]
                snapshot_count = len(snapshots)

                if snapshot_count > 1:
                    vals = [float(s.get('total_portfolio_value') or 0) for s in snapshots]
                    returns = [(vals[i] - vals[i-1]) / vals[i-1]
                              for i in range(1, len(vals)) if vals[i-1] != 0]

                    if returns:
                        mean_r = self._mean(returns)
                        std_r = self._std(returns)
                        if std_r > 0:
                            sharpe_ratio = (mean_r / std_r) * math.sqrt(252)

                        downside = [r for r in returns if r < 0]
                        dv = self._std(downside) if downside else 0.0
                        if dv > 0:
                            sortino_ratio = (mean_r / dv) * math.sqrt(252)

                        max_dd_pct = self._max_drawdown_pct(returns)

                    # Compounded return
                    if vals[0] > 0 and vals[-1] > 0:
                        total_return_pct = (vals[-1] / vals[0] - 1) * 100
            except (psycopg2.Error, Exception) as e:
                logger.warning(f"Failed to fetch portfolio snapshots: {e}")

            # Streak analysis
            best_win_streak = worst_loss_streak = current_streak = 0
            if pnl_dollars:
                cur_run = 0
                best_w = best_l = 0
                for p in reversed(pnl_dollars):
                    if p > 0:
                        cur_run = max(0, cur_run) + 1
                    elif p < 0:
                        cur_run = min(0, cur_run) - 1
                    best_w = max(best_w, cur_run)
                    best_l = min(best_l, cur_run)
                current_streak = cur_run
                best_win_streak = best_w
                worst_loss_streak = abs(best_l)

            # Confidence levels
            if snapshot_count >= 20:
                sharpe_confidence = 'high'
            elif snapshot_count >= 5:
                sharpe_confidence = 'medium'
            else:
                sharpe_confidence = 'low'

            if win_loss_total >= 30:
                win_rate_confidence = 'high'
            elif win_loss_total >= 10:
                win_rate_confidence = 'medium'
            else:
                win_rate_confidence = 'low'

            return {
                'total_trades': total,
                'winning_trades': winning,
                'losing_trades': losing,
                'breakeven_trades': breakeven,
                'win_rate_pct': round(win_rate_pct, 2),
                'win_rate_confidence': win_rate_confidence,
                'profit_factor': round(profit_factor, 2),
                'total_pnl_dollars': round(sum(pnl_dollars), 2),
                'total_pnl_pct': round(sum(pnl_pcts), 2),
                'total_return_pct': round(total_return_pct, 2) if total_return_pct else None,
                'avg_win_pct': round(avg_win_pct, 2),
                'avg_loss_pct': round(avg_loss_pct, 2),
                'best_trade_pct': round(max(pnl_pcts), 2) if pnl_pcts else None,
                'worst_trade_pct': round(min(pnl_pcts), 2) if pnl_pcts else None,
                'sharpe_ratio': round(sharpe_ratio, 2) if sharpe_ratio is not None else None,
                'sharpe_confidence': sharpe_confidence,
                'sortino_ratio': round(sortino_ratio, 2) if sortino_ratio is not None else None,
                'max_drawdown_pct': round(abs(max_dd_pct) * 100, 2) if max_dd_pct is not None else None,
                'expectancy_r': round(self._mean(r_multiples), 2) if r_multiples else None,
                'avg_holding_days': round(self._mean(holding_days), 1) if holding_days else None,
                'current_streak': current_streak if pnl_dollars else None,
                'best_win_streak': best_win_streak if pnl_dollars else None,
                'worst_loss_streak': worst_loss_streak if pnl_dollars else None,
                'portfolio_snapshots': snapshot_count,
                '_source': 'database_direct',
            }
        except (psycopg2.Error, Exception) as e:
            logger.error(f"fetch_performance_metrics failed: {type(e).__name__}: {e}")
            return {
                '_error': str(e),
                '_source': 'database_direct',
                'total_trades': 0,
            }

    def _empty_performance_response(self) -> Dict[str, Any]:
        """Return empty performance response when no trades exist. Returns None for metrics without sufficient data."""
        return {
            'total_trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'breakeven_trades': 0,
            'win_rate_pct': None,
            'win_rate_confidence': 'low',
            'profit_factor': None,
            'total_pnl_dollars': None,
            'total_pnl_pct': None,
            'total_return_pct': None,
            'avg_win_pct': None,
            'avg_loss_pct': None,
            'best_trade_pct': None,
            'worst_trade_pct': None,
            'sharpe_ratio': None,
            'sharpe_confidence': 'low',
            'sortino_ratio': None,
            'max_drawdown_pct': None,
            'expectancy_r': None,
            'avg_holding_days': None,
            'current_streak': None,
            'best_win_streak': None,
            'worst_loss_streak': None,
            'portfolio_snapshots': 0,
            '_source': 'database_direct',
        }

    def fetch_open_positions(self) -> Dict[str, Any]:
        """Fetch all open positions with current prices and calculated P&L.

        Returns:
            Dict with 'items' list on success, '_error' on failure
        """
        try:
            self.cursor.execute("""
                SELECT
                    at.symbol,
                    at.entry_price as avg_entry_price,
                    COALESCE(pd.close, at.entry_price) as current_price,
                    CASE
                        WHEN at.entry_price > 0
                        THEN (((COALESCE(pd.close, at.entry_price) - at.entry_price) / at.entry_price) * 100)
                        ELSE 0
                    END as unrealized_pnl_pct,
                    (at.entry_quantity * COALESCE(pd.close, at.entry_price))::DECIMAL(14,2) as position_value,
                    at.entry_quantity as quantity,
                    at.stop_loss_price,
                    at.target_1_price,
                    at.target_2_price,
                    at.target_3_price,
                    cp.sector,
                    at.trade_id,
                    at.trade_date as created_at,
                    'open' as status
                FROM algo_trades at
                LEFT JOIN (
                    SELECT DISTINCT ON (symbol) symbol, close
                    FROM price_daily
                    ORDER BY symbol, date DESC
                ) pd ON at.symbol = pd.symbol
                LEFT JOIN company_profile cp ON cp.ticker = at.symbol
                WHERE at.exit_price IS NULL
                ORDER BY position_value DESC NULLS LAST
            """)
            rows = self.cursor.fetchall()

            positions = []
            for row in rows:
                d = dict(row)

                # Compute unrealized P&L in dollars
                position_value = d.get('position_value')
                unrealized_pnl_pct = d.get('unrealized_pnl_pct')
                if position_value is not None and unrealized_pnl_pct is not None:
                    d['unrealized_pnl'] = round(
                        float(position_value) * float(unrealized_pnl_pct) / 100, 2
                    )
                else:
                    d['unrealized_pnl'] = None

                # Compute R multiple (current price relative to stop loss)
                avg_entry = d.get('avg_entry_price')
                stop_loss = d.get('stop_loss_price')
                current = d.get('current_price', avg_entry)

                if (avg_entry and stop_loss and
                    float(avg_entry) > float(stop_loss or 0)):
                    d['r_multiple'] = round(
                        (float(current or avg_entry) - float(avg_entry)) /
                        (float(avg_entry) - float(stop_loss)),
                        2
                    )
                else:
                    d['r_multiple'] = None

                positions.append(d)

            logger.debug(f"fetch_open_positions: {len(positions)} open positions found")
            return {'items': positions, '_source': 'database_direct'}

        except (psycopg2.Error, Exception) as e:
            logger.error(f"fetch_open_positions failed: {type(e).__name__}: {e}")
            return {'_error': str(e), '_source': 'database_direct', 'items': []}

    def fetch_recent_trades(self, limit: int = 50) -> Dict[str, Any]:
        """Fetch recent closed trades.

        Args:
            limit: Maximum number of trades to return

        Returns:
            Dict with 'items' list on success, '_error' on failure
        """
        try:
            self.cursor.execute("""
                SELECT trade_id, symbol, trade_date, exit_date,
                       entry_price, exit_price, entry_quantity,
                       profit_loss_dollars, profit_loss_pct, exit_r_multiple,
                       stop_loss_price, target_1_price, target_2_price, target_3_price
                FROM algo_trades
                WHERE exit_date IS NOT NULL
                ORDER BY exit_date DESC
                LIMIT %s
            """, (limit,))
            trades = [dict(row) for row in self.cursor.fetchall()]
            logger.debug(f"fetch_recent_trades: {len(trades)} trades found")
            return {'items': trades, '_source': 'database_direct'}

        except (psycopg2.Error, Exception) as e:
            logger.error(f"fetch_recent_trades failed: {type(e).__name__}: {e}")
            return {'_error': str(e), '_source': 'database_direct', 'items': []}

    def fetch_equity_curve(self, limit: int = 252) -> Dict[str, Any]:
        """Fetch equity curve (portfolio values over time).

        Args:
            limit: Maximum number of snapshots to return (default 252 = ~1 year)

        Returns:
            Dict with 'equity_vals' list on success, '_error' on failure
        """
        try:
            self.cursor.execute("""
                SELECT snapshot_date, total_portfolio_value
                FROM algo_portfolio_snapshots
                ORDER BY snapshot_date ASC
                LIMIT %s
            """, (limit,))
            rows = [dict(row) for row in self.cursor.fetchall()]
            values = [float(r.get('total_portfolio_value') or 0) for r in rows]
            logger.debug(f"fetch_equity_curve: {len(values)} snapshots found")
            return {'equity_vals': values, '_source': 'database_direct'}

        except (psycopg2.Error, Exception) as e:
            logger.error(f"fetch_equity_curve failed: {type(e).__name__}: {e}")
            return {'_error': str(e), '_source': 'database_direct', 'equity_vals': []}

    def fetch_recent_returns(self, limit: int = 252) -> Dict[str, Any]:
        """Fetch recent daily returns from portfolio snapshots.

        Args:
            limit: Maximum number of return periods to calculate (default 252 = ~1 year)

        Returns:
            Dict with 'recent_rets' list on success, '_error' on failure
        """
        try:
            self.cursor.execute("""
                SELECT snapshot_date, total_portfolio_value
                FROM algo_portfolio_snapshots
                ORDER BY snapshot_date ASC
                LIMIT %s
            """, (limit,))
            rows = [dict(row) for row in self.cursor.fetchall()]
            vals = [float(r.get('total_portfolio_value') or 0) for r in rows]

            if len(vals) < 2:
                return {'recent_rets': [], '_source': 'database_direct'}

            returns = [(vals[i] - vals[i-1]) / vals[i-1]
                      for i in range(1, len(vals)) if vals[i-1] != 0]
            logger.debug(f"fetch_recent_returns: {len(returns)} daily returns calculated")
            return {'recent_rets': returns, '_source': 'database_direct'}

        except (psycopg2.Error, Exception) as e:
            logger.error(f"fetch_recent_returns failed: {type(e).__name__}: {e}")
            return {'_error': str(e), '_source': 'database_direct', 'recent_rets': []}
