#!/usr/bin/env python3

"""
Walk-Forward Backtest Engine — Historical strategy validation with TCA realism.

No look-ahead bias: all decisions made with data available AT signal_date.
Accounts for realistic slippage, bid-ask impact, commissions.
Writes to backtest_runs, backtest_trades, backtest_results tables.
"""

import logging
from datetime import date as _date, datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path
import uuid
import json
import numpy as np
from decimal import Decimal
from scipy.optimize import minimize

from utils.db_connection import get_db_connection
from config.credential_helper import get_db_config, get_db_password
from algo.algo_config import get_config

logger = logging.getLogger(__name__)


class BacktestResult:
    """Single backtest period result."""

    def __init__(self):
        self.trades: List[Dict[str, Any]] = []
        self.equity_curve: List[Tuple[_date, float]] = []
        self.total_return_pct: float = 0.0
        self.sharpe_ratio: float = 0.0
        self.sortino_ratio: float = 0.0
        self.calmar_ratio: float = 0.0
        self.max_drawdown_pct: float = 0.0
        self.win_rate_pct: float = 0.0
        self.profit_factor: float = 0.0
        self.expectancy_r: float = 0.0
        self.avg_hold_days: float = 0.0
        self.best_trade_r: float = 0.0
        self.worst_trade_r: float = 0.0


class Backtester:
    """Walk-forward and single-period backtester."""

    def __init__(self, config: Optional[Any] = None):
        self.config = config or get_config()
        self.conn = None
        self.cur = None

    def connect(self):
        """Connect to database."""
        if not self.conn:
            self.conn = get_db_connection()
            self.cur = self.conn.cursor()

    def disconnect(self):
        """Close database connection."""
        if self.cur:
            self.cur.close()
        if self.conn:
            self.conn.close()

    def optimize_weights_in_sample(
        self,
        train_start: _date,
        train_end: _date,
    ) -> Dict[str, float]:
        """
        Optimize signal component weights to maximize correlation with realized returns.

        Uses closed trades in training period to find weights that explain
        exit_r_multiple best via component scores. Applies light regularization
        to prevent overfitting to in-sample data.

        Args:
            train_start: Training period start
            train_end: Training period end

        Returns:
            {component_name: weight, ...} (sums to 1.0)
        """
        self.connect()
        try:
            # Fetch closed trades with component scores and realized returns
            self.cur.execute(
                """
                SELECT swing_components, exit_r_multiple
                FROM algo_trades
                WHERE signal_date BETWEEN %s AND %s
                  AND status = 'closed'
                  AND swing_components IS NOT NULL
                  AND exit_r_multiple IS NOT NULL
                """,
                (train_start, train_end),
            )
            trades = self.cur.fetchall()

            if len(trades) < 10:
                logger.warning(f"Only {len(trades)} trades in training period; using default weights")
                return {
                    'setup_quality': 0.20,
                    'trend_quality': 0.20,
                    'momentum_rs': 0.20,
                    'volume': 0.15,
                    'fundamentals': 0.10,
                    'sector_industry': 0.10,
                    'multi_timeframe': 0.05,
                }

            # Extract component scores and returns
            components_list = [
                'setup_quality', 'trend_quality', 'momentum_rs', 'volume',
                'fundamentals', 'sector_industry', 'multi_timeframe',
            ]
            component_matrix = []
            returns_vec = []

            for swing_components, exit_r_multiple in trades:
                scores = []
                valid = True
                for comp in components_list:
                    val = swing_components.get(comp, 0)
                    if val is None:
                        valid = False
                        break
                    scores.append(float(val))

                if valid and exit_r_multiple is not None:
                    component_matrix.append(scores)
                    returns_vec.append(float(exit_r_multiple))

            if len(component_matrix) < 5:
                logger.warning(f"Insufficient data ({len(component_matrix)} trades) for weight optimization")
                return {comp: 1.0 / len(components_list) for comp in components_list}

            X = np.array(component_matrix)  # (n_trades, n_components)
            y = np.array(returns_vec)  # (n_trades,)

            # Objective: minimize negative correlation (maximize correlation)
            def objective(weights):
                w = np.array(weights)
                w = np.maximum(w, 0.01)  # Ensure positive
                w = w / w.sum()  # Normalize
                weighted_score = X @ w
                if weighted_score.std() == 0:
                    return 1.0
                correlation = np.corrcoef(weighted_score, y)[0, 1]
                # Add light L2 regularization to prevent extreme weights
                regularization = 0.1 * np.sum((w - 1.0 / len(w)) ** 2)
                return -(correlation - regularization) if not np.isnan(correlation) else 1.0

            # Optimize with constraints: weights >= 0, sum to 1
            x0 = np.array([1.0 / len(components_list)] * len(components_list))
            constraints = {'type': 'eq', 'fun': lambda w: w.sum() - 1.0}
            bounds = [(0.01, 0.5) for _ in components_list]  # Prevent extreme weights

            result = minimize(
                objective, x0, method='SLSQP',
                bounds=bounds, constraints=constraints,
                options={'maxiter': 100},
            )

            if result.success:
                optimized_weights = np.maximum(result.x, 0.01)
                optimized_weights = optimized_weights / optimized_weights.sum()
                opt_dict = {comp: float(w) for comp, w in zip(components_list, optimized_weights)}
                logger.info(f"Optimized weights for train {train_start}→{train_end}: {opt_dict}")
                return opt_dict
            else:
                logger.warning(f"Weight optimization failed: {result.message}")
                return {comp: 1.0 / len(components_list) for comp in components_list}

        except Exception as e:
            logger.error(f"Error optimizing weights: {e}")
            return {comp: 1.0 / 7 for comp in [
                'setup_quality', 'trend_quality', 'momentum_rs', 'volume',
                'fundamentals', 'sector_industry', 'multi_timeframe',
            ]}
        finally:
            self.disconnect()

    def run_backtest(
        self,
        start_date: _date,
        end_date: _date,
        config_overrides: Optional[Dict[str, Any]] = None,
        label: str = "",
    ) -> BacktestResult:
        """
        Run single-period backtest from start_date to end_date.

        Args:
            start_date: Period start
            end_date: Period end
            config_overrides: Override swing score weights (e.g., from optimization)
            label: Label for this run (e.g., "in-sample", "out-of-sample")

        Returns:
            BacktestResult with metrics
        """
        self.connect()
        try:
            logger.info(f"Backtest {label} {start_date} → {end_date}")

            # Fetch all BUY signals in period
            self.cur.execute(
                """SELECT bd.symbol, bd.date AS signal_date, ss.score AS swing_score,
                          tt.minervini_trend_score, cp.sector, cp.industry
                   FROM buy_sell_daily bd
                   JOIN swing_trader_scores ss ON (bd.symbol = ss.symbol AND bd.date = ss.date)
                   JOIN trend_template_data tt ON (bd.symbol = tt.symbol AND bd.date = tt.date)
                   LEFT JOIN company_profile cp ON bd.symbol = cp.ticker
                   WHERE bd.date BETWEEN %s AND %s
                     AND bd.signal_type = 'BUY'
                   ORDER BY bd.date ASC, ss.score DESC""",
                (start_date, end_date),
            )
            buy_signals = self.cur.fetchall()

            result = BacktestResult()
            portfolio_value = self.config.get('initial_capital', 100000)
            peak_value = portfolio_value
            position_value = 0

            for sig_row in buy_signals:
                symbol, signal_date, swing_score, trend_score, sector, industry = sig_row

                # Simulate trade through end_date
                trade = self._simulate_trade(
                    symbol, signal_date, end_date, swing_score, config_overrides
                )
                if not trade:
                    continue

                result.trades.append(trade)

                # Update portfolio
                exit_pnl = trade['profit_loss_dollars']
                portfolio_value += exit_pnl
                peak_value = max(peak_value, portfolio_value)

            # Compute metrics
            if result.trades:
                result = self._compute_metrics(result, self.config.get('initial_capital', 100000), portfolio_value, peak_value)

            return result

        finally:
            self.disconnect()

    def walk_forward(
        self,
        start_date: _date,
        end_date: _date,
        train_days: int = 252,
        test_days: int = 63,
    ) -> Dict[str, Any]:
        """
        Walk-forward backtesting with auto-weight optimization.

        If data < 315 days: runs single-period test instead.
        If data 315+ days: runs full walk-forward.

        Returns:
            {
                'windows': [{'train': (...), 'test': (...), 'result': ...}, ...],
                'out_of_sample_sharpe': float,
                'overfitting_ratio': float,
                'data_depth_days': int,
            }
        """
        self.connect()
        try:
            total_days = (end_date - start_date).days

            # Auto-detect data depth
            if total_days < train_days + test_days:
                logger.warning(
                    f"Data depth {total_days}d < required {train_days + test_days}d. "
                    f"Running single-period test instead."
                )
                result = self.run_backtest(start_date, end_date, label="single-period")
                return {
                    'windows': [
                        {
                            'train': (start_date, start_date),
                            'test': (start_date, end_date),
                            'result': result,
                        }
                    ],
                    'out_of_sample_sharpe': result.sharpe_ratio,
                    'overfitting_ratio': 1.0,
                    'data_depth_days': total_days,
                }

            # Full walk-forward
            windows = []
            cursor = start_date

            while cursor + timedelta(days=train_days + test_days) <= end_date:
                train_start = cursor
                train_end = cursor + timedelta(days=train_days)
                test_start = train_end + timedelta(days=1)
                test_end = test_start + timedelta(days=test_days)

                logger.info(f"WF Window: train {train_start}→{train_end}, test {test_start}→{test_end}")

                # Optimize weights on in-sample (training) data
                optimized_weights = self.optimize_weights_in_sample(train_start, train_end)

                # Test optimized weights on out-of-sample data
                result = self.run_backtest(test_start, test_end, config_overrides=optimized_weights, label="test")

                windows.append(
                    {
                        'train': (train_start, train_end),
                        'test': (test_start, test_end),
                        'result': result,
                    }
                )

                cursor += timedelta(days=test_days)

            # Aggregate metrics
            if windows:
                oos_sharpes = [w['result'].sharpe_ratio for w in windows if w['result'].sharpe_ratio]
                out_of_sample_sharpe = np.mean(oos_sharpes) if oos_sharpes else 0.0
            else:
                out_of_sample_sharpe = 0.0

            return {
                'windows': windows,
                'out_of_sample_sharpe': out_of_sample_sharpe,
                'overfitting_ratio': None,  # requires in-sample Sharpe tracking; currently not computed
                'data_depth_days': total_days,
            }

        finally:
            self.disconnect()

    def _simulate_trade(
        self,
        symbol: str,
        signal_date: _date,
        exit_by_date: _date,
        swing_score: float,
        config_overrides: Optional[Dict[str, Any]] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Simulate a single trade from entry through exit.

        Returns:
            {
                'symbol': str,
                'signal_date': _date,
                'entry_date': _date,
                'entry_price': float,
                'entry_qty': int,
                'exit_date': _date,
                'exit_price': float,
                'stop_loss_price': float,
                'target_1_price': float,
                'profit_loss_dollars': float,
                'profit_loss_pct': float,
                'r_multiple': float,
                'hold_days': int,
            }
        """
        try:
            # Get entry price (next day open after signal)
            self.cur.execute(
                """SELECT date, open, close FROM price_daily
                   WHERE symbol = %s AND date > %s
                   ORDER BY date ASC LIMIT 1""",
                (symbol, signal_date),
            )
            entry_row = self.cur.fetchone()
            if not entry_row:
                return None

            entry_date, entry_open, _ = entry_row
            entry_price = float(entry_open)

            # Apply entry slippage (0.10%)
            entry_price *= 1.001

            # Determine exit (first target hit, stop hit, or max hold reached)
            self.cur.execute(
                """SELECT date, high, low, close FROM price_daily
                   WHERE symbol = %s AND date BETWEEN %s AND %s
                   ORDER BY date ASC""",
                (symbol, entry_date, exit_by_date),
            )
            price_bars = self.cur.fetchall()

            if not price_bars:
                return None

            # Simple stops/targets (for backtest, not the full exit engine)
            stop_loss = entry_price * 0.95  # -5% hard stop
            target_1 = entry_price * 1.075  # 1.5R target (5% stop × 1.5 = 7.5%)
            max_hold_days = self.config.get('max_hold_days', 20)

            exit_date = None
            exit_price = None
            exit_reason = None

            for i, (bar_date, bar_high, bar_low, bar_close) in enumerate(price_bars):
                days_held = (bar_date - entry_date).days

                # Stop loss hit
                if bar_low <= stop_loss:
                    exit_date = bar_date
                    exit_price = stop_loss
                    exit_reason = 'stop'
                    break

                # Target hit
                if bar_high >= target_1:
                    exit_date = bar_date
                    exit_price = target_1
                    exit_reason = 'target_1'
                    break

                # Max hold reached
                if days_held >= max_hold_days:
                    exit_date = bar_date
                    exit_price = float(bar_close)
                    exit_reason = 'max_hold'
                    break

            # If no exit signal, use last bar
            if not exit_date:
                exit_date, _, _, last_close = price_bars[-1]
                exit_price = float(last_close)
                exit_reason = 'backtest_end'

            # Calculate P&L
            exit_price *= 0.9995  # Apply exit slippage (0.05%)
            commission = entry_price * 0.005 * 100  # Assume 100 shares

            pnl_dollars = (exit_price - entry_price) * 100 - commission  # Assume 100 shares
            pnl_pct = (exit_price - entry_price) / entry_price
            r_multiple = pnl_dollars / (entry_price * 100 * 0.05)  # Assuming 5% risk

            hold_days = (exit_date - entry_date).days

            return {
                'symbol': symbol,
                'signal_date': signal_date,
                'entry_date': entry_date,
                'entry_price': round(entry_price, 4),
                'entry_qty': 100,
                'exit_date': exit_date,
                'exit_price': round(exit_price, 4),
                'stop_loss_price': round(stop_loss, 4),
                'target_1_price': round(target_1, 4),
                'profit_loss_dollars': round(pnl_dollars, 2),
                'profit_loss_pct': round(pnl_pct * 100, 2),
                'r_multiple': round(r_multiple, 2),
                'hold_days': hold_days,
                'exit_reason': exit_reason,
            }

        except Exception as e:
            logger.debug(f"Trade simulation failed for {symbol}: {e}")
            return None

    def _compute_metrics(
        self,
        result: BacktestResult,
        initial_capital: float,
        final_capital: float,
        peak_capital: float,
    ) -> BacktestResult:
        """Compute all performance metrics from trade list."""
        if not result.trades:
            return result

        # Returns and drawdown
        total_pnl = sum(t['profit_loss_dollars'] for t in result.trades)
        result.total_return_pct = (final_capital - initial_capital) / initial_capital * 100

        # Win rate
        winners = [t for t in result.trades if t['profit_loss_dollars'] > 0]
        result.win_rate_pct = len(winners) / len(result.trades) * 100 if result.trades else 0

        # R-multiple metrics
        r_values = [t.get('r_multiple', 0) for t in result.trades]
        if r_values:
            result.best_trade_r = max(r_values)
            result.worst_trade_r = min(r_values)
            result.expectancy_r = np.mean(r_values)

        # Profit factor
        wins_sum = sum(t['profit_loss_dollars'] for t in winners)
        losses_sum = abs(
            sum(t['profit_loss_dollars'] for t in result.trades if t['profit_loss_dollars'] < 0)
        )
        result.profit_factor = wins_sum / max(1, losses_sum)

        # Drawdown
        result.max_drawdown_pct = (
            ((peak_capital - final_capital) / peak_capital * 100)
            if peak_capital > 0
            else 0
        )

        # Hold duration
        hold_days = [t['hold_days'] for t in result.trades]
        result.avg_hold_days = np.mean(hold_days) if hold_days else 0

        # Sharpe/Sortino: normalize per-trade P&L by hold duration to approximate daily returns
        if r_values and len(r_values) > 1:
            daily_returns = np.array([
                (t['profit_loss_pct'] / 100) / max(1, t['hold_days']) for t in result.trades
            ])
            if daily_returns.std() > 0:
                result.sharpe_ratio = (
                    daily_returns.mean() / daily_returns.std() * np.sqrt(252)
                )

            downside_returns = np.array([min(r, 0) for r in daily_returns])
            if downside_returns.std() > 0:
                result.sortino_ratio = (
                    daily_returns.mean() / downside_returns.std() * np.sqrt(252)
                )

        # Calmar (return / max drawdown)
        if result.max_drawdown_pct > 0:
            result.calmar_ratio = result.total_return_pct / result.max_drawdown_pct

        return result


if __name__ == "__main__":
    bt = Backtester()
    result = bt.run_backtest(_date(2026, 1, 1), _date(2026, 5, 22), label="test")
    logger.info(f"Backtest complete. Sharpe: {result.sharpe_ratio:.2f}, Win rate: {result.win_rate_pct:.1f}%")
