#!/usr/bin/env python3

"""
Backtester Module — Walk-forward optimization and historical performance validation

This module backtests the orchestrator's trading logic against historical market data.

Features:
- Load historical price data from database
- Simulate trading signals using the signal generation logic
- Track portfolio metrics (Sharpe ratio, drawdown, win rate)
- Support walk-forward optimization with WFE metric
- Crisis scenario testing

Walk-Forward Optimization (WFO):
- Split historical period into anchored walk-forward windows
- In-sample: optimize parameters on window
- Out-of-sample: validate on next window
- Calculate Walk-Forward Efficiency (WFE) = out-of-sample / in-sample Sharpe
- Warn if WFE < 0.5 (curve-fitting detected)
"""

from config.credential_helper import get_db_password, get_db_config

import os
import sys
import json
import psycopg2
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime, date as _date, timedelta
from typing import Dict, List, Any, Optional, Tuple
import argparse
from collections import defaultdict
import statistics
from utils.structured_logger import get_logger

logger = get_logger(__name__)

env_file = Path(__file__).parent / '.env.local'
if not env_file.exists():  # fallback: root when running from subdirectory
    env_file = Path(__file__).parent.parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

# Get DB password from environment first, fall back to credential manager if needed
db_password = os.getenv("DB_PASSWORD")
if not db_password:
    try:
        from config.credential_manager import get_credential_manager
        credential_manager = get_credential_manager()
        db_password = get_db_password()
    except Exception:
        db_password = "postgres"  # Default for local dev

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "user": os.getenv("DB_USER", "stocks"),
    "password": db_password,
    "database": os.getenv("DB_NAME", "stocks"),
}


class Backtester:
    """Backtest trading strategy against historical data."""

    def __init__(
        self,
        start_date: _date,
        end_date: _date,
        initial_capital: float = 100_000.0,
        max_positions: int = 12,
        use_advanced_filters: bool = True,
        verbose: bool = False,
    ):
        self.start_date = start_date
        self.end_date = end_date
        self.initial_capital = initial_capital
        self.max_positions = max_positions
        self.use_advanced_filters = use_advanced_filters
        self.verbose = verbose

        self.conn = None
        self.portfolio_value = initial_capital
        self.cash = initial_capital
        self.positions = {}  # symbol -> {shares, entry_price, entry_date}
        self.trades = []  # list of {symbol, entry_price, exit_price, shares, entry_date, exit_date, pnl, return}
        self.daily_values = []  # list of {date, value, cash, position_count}
        self.max_portfolio_value = initial_capital
        self.min_portfolio_value = initial_capital

    def connect(self):
        """Connect to database."""
        try:
            self.conn = psycopg2.connect(**DB_CONFIG)
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise

    def disconnect(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()

    def _load_price_data(self) -> Dict[str, List[Tuple]]:
        """Load price data for all symbols in date range."""
        cur = self.conn.cursor()
        query = """
            SELECT symbol, date, close
            FROM price_daily
            WHERE date >= %s AND date <= %s
            ORDER BY symbol, date
        """
        cur.execute(query, (self.start_date, self.end_date))

        price_data = defaultdict(list)
        for symbol, price_date, close_price in cur.fetchall():
            price_data[symbol].append((price_date, float(close_price)))

        cur.close()
        return dict(price_data)

    def _load_trading_dates(self) -> List[_date]:
        """Get sorted list of trading dates in range."""
        cur = self.conn.cursor()
        query = """
            SELECT DISTINCT date
            FROM price_daily
            WHERE date >= %s AND date <= %s
            ORDER BY date
        """
        cur.execute(query, (self.start_date, self.end_date))
        dates = [row[0] for row in cur.fetchall()]
        cur.close()
        return dates

    def _get_signals_for_date(self, trade_date: _date) -> List[Tuple[str, float]]:
        """
        Get trading signals for a specific date.
        Returns list of (symbol, signal_score) tuples.

        For now, use a simple momentum-based signal:
        - Calculate 20-day momentum for each stock
        - Return top N by momentum
        """
        cur = self.conn.cursor()

        # Get 20-day momentum for all stocks as of this date
        query = """
            WITH price_window AS (
                SELECT symbol, close, date,
                       LAG(close) OVER (PARTITION BY symbol ORDER BY date) as prev_close
                FROM price_daily
                WHERE date <= %s AND date > %s - interval '25 days'
            )
            SELECT symbol,
                   ROUND(100.0 * (MAX(close) - MIN(close)) / MIN(close), 2) as momentum
            FROM price_window
            GROUP BY symbol
            HAVING COUNT(*) >= 15
            ORDER BY momentum DESC
            LIMIT %s
        """

        cur.execute(query, (trade_date, trade_date, self.max_positions * 2))
        signals = [(row[0], row[1]) for row in cur.fetchall()]
        cur.close()

        return signals

    def _update_positions(self, trade_date: _date, price_data: Dict[str, List[Tuple]]):
        """Update current position P&L based on today's prices."""
        closed_positions = []

        for symbol in list(self.positions.keys()):
            if symbol not in price_data:
                continue

            # Find price for this date
            close_price = None
            for pd, price in price_data[symbol]:
                if pd == trade_date:
                    close_price = price
                    break

            if close_price is None:
                continue

            pos = self.positions[symbol]
            current_value = pos['shares'] * close_price
            entry_value = pos['shares'] * pos['entry_price']
            pnl = current_value - entry_value
            pos['current_price'] = close_price
            pos['current_value'] = current_value
            pos['pnl'] = pnl

            # Simple exit logic: exit if > 5% gain or < 3% loss
            if pnl > entry_value * 0.05 or pnl < -entry_value * 0.03:
                closed_positions.append(symbol)

        # Close positions
        for symbol in closed_positions:
            pos = self.positions[symbol]
            trade = {
                'symbol': symbol,
                'entry_price': pos['entry_price'],
                'exit_price': pos['current_price'],
                'shares': pos['shares'],
                'entry_date': pos['entry_date'],
                'exit_date': trade_date,
                'pnl': pos['pnl'],
                'return_pct': (pos['pnl'] / (pos['shares'] * pos['entry_price'])) * 100,
            }
            self.trades.append(trade)
            self.cash += pos['current_value']
            del self.positions[symbol]

    def _execute_entries(self, trade_date: _date, signals: List[Tuple[str, float]], price_data: Dict[str, List[Tuple]]):
        """Execute entry trades based on signals."""
        open_slots = self.max_positions - len(self.positions)

        for symbol, score in signals[:open_slots]:
            if symbol in self.positions:
                continue

            # Get price for this date
            if symbol not in price_data:
                continue

            entry_price = None
            for pd, price in price_data[symbol]:
                if pd == trade_date:
                    entry_price = price
                    break

            if entry_price is None or entry_price == 0:
                continue

            # Allocate 1/max_positions of capital per position
            position_size = self.cash / (open_slots + 1)
            shares = int(position_size / entry_price)

            if shares > 0:
                cost = shares * entry_price
                self.positions[symbol] = {
                    'shares': shares,
                    'entry_price': entry_price,
                    'entry_date': trade_date,
                    'current_price': entry_price,
                    'current_value': cost,
                    'pnl': 0,
                }
                self.cash -= cost

    def _calculate_portfolio_value(self) -> float:
        """Calculate total portfolio value."""
        position_value = sum(pos['current_value'] for pos in self.positions.values())
        return self.cash + position_value

    def run(self) -> Dict[str, Any]:
        """Run backtest and return metrics."""
        logger.info(f"Backtesting {self.start_date} to {self.end_date}")
        logger.info(f"Initial capital: ${self.initial_capital:,.0f}")
        logger.info(f"Max positions: {self.max_positions}")

        self.connect()

        try:
            # Load historical data
            price_data = self._load_price_data()
            trading_dates = self._load_trading_dates()

            if not trading_dates:
                self.disconnect()
                return {
                    'status': 'ERROR',
                    'error': 'No price data available for date range',
                }

            # Simulate trading for each day
            for i, trade_date in enumerate(trading_dates):
                # Update existing positions
                self._update_positions(trade_date, price_data)

                # Get signals and execute entries
                signals = self._get_signals_for_date(trade_date)
                self._execute_entries(trade_date, signals, price_data)

                # Record daily portfolio value
                portfolio_value = self._calculate_portfolio_value()
                self.daily_values.append({
                    'date': trade_date,
                    'value': portfolio_value,
                    'cash': self.cash,
                    'position_count': len(self.positions),
                })

                # Track min/max for drawdown
                self.max_portfolio_value = max(self.max_portfolio_value, portfolio_value)
                self.min_portfolio_value = min(self.min_portfolio_value, portfolio_value)

                if self.verbose and (i + 1) % 20 == 0:
                    logger.debug(f"Day {i+1}/{len(trading_dates)}: "
                          f"Portfolio=${portfolio_value:,.0f}, Positions={len(self.positions)}")

            # Calculate metrics
            metrics = self._calculate_metrics()

            # Save results to database if successful
            if metrics.get('status') == 'OK':
                self.save_results_to_db(metrics, strategy_name='momentum')

        finally:
            self.disconnect()

        return metrics

    def _calculate_metrics(self) -> Dict[str, Any]:
        """Calculate backtest performance metrics."""
        if not self.daily_values:
            return {'status': 'ERROR', 'error': 'No daily values'}

        # Close remaining positions at final price
        if self.positions:
            final_date = self.daily_values[-1]['date']
            for symbol in list(self.positions.keys()):
                pos = self.positions[symbol]
                trade = {
                    'symbol': symbol,
                    'entry_price': pos['entry_price'],
                    'exit_price': pos['current_price'],
                    'shares': pos['shares'],
                    'entry_date': pos['entry_date'],
                    'exit_date': final_date,
                    'pnl': pos['pnl'],
                    'return_pct': (pos['pnl'] / (pos['shares'] * pos['entry_price'])) * 100,
                }
                self.trades.append(trade)

        # Portfolio metrics
        final_value = self.daily_values[-1]['value']
        total_return = final_value - self.initial_capital
        total_return_pct = (total_return / self.initial_capital) * 100

        # Drawdown
        peak = self.max_portfolio_value
        trough = self.min_portfolio_value
        max_drawdown = (trough - peak) / peak * 100 if peak > 0 else 0

        # Daily returns for Sharpe ratio
        daily_returns = []
        for i in range(1, len(self.daily_values)):
            prev = self.daily_values[i-1]['value']
            curr = self.daily_values[i]['value']
            daily_return = (curr - prev) / prev if prev > 0 else 0
            daily_returns.append(daily_return)

        # Sharpe ratio (annualized)
        if daily_returns and len(daily_returns) > 1:
            avg_return = statistics.mean(daily_returns)
            std_return = statistics.stdev(daily_returns)
            sharpe_ratio = (avg_return / std_return * 252**0.5) if std_return > 0 else 0
        else:
            sharpe_ratio = 0

        # Trade metrics
        closed_trades = len(self.trades)
        winning_trades = sum(1 for t in self.trades if t['pnl'] > 0)
        win_rate = (winning_trades / closed_trades * 100) if closed_trades > 0 else 0

        # R-multiple and profit factor calculations
        winning_pnl = sum(t['pnl'] for t in self.trades if t['pnl'] > 0)
        losing_pnl = sum(t['pnl'] for t in self.trades if t['pnl'] < 0)
        profit_factor = abs(winning_pnl / losing_pnl) if losing_pnl != 0 else 0

        # Average R-multiple (estimate from return percentages)
        winning_trades_list = [t for t in self.trades if t['pnl'] > 0]
        losing_trades_list = [t for t in self.trades if t['pnl'] < 0]

        avg_win_r = statistics.mean([t['return_pct'] for t in winning_trades_list]) / 100 if winning_trades_list else 0
        avg_loss_r = statistics.mean([t['return_pct'] for t in losing_trades_list]) / 100 if losing_trades_list else 0

        # Expectancy = (win% × avg_win) - (loss% × avg_loss)
        win_pct = winning_trades / closed_trades if closed_trades > 0 else 0
        loss_pct = 1 - win_pct
        expectancy_r = (win_pct * avg_win_r) - (loss_pct * abs(avg_loss_r)) if closed_trades > 0 else 0

        avg_r_per_trade = statistics.mean([t['return_pct'] / 100 for t in self.trades]) if self.trades else 0

        # Days in backtest
        days_in_test = (self.daily_values[-1]['date'] - self.daily_values[0]['date']).days

        results = {
            'status': 'OK',
            'start_date': str(self.start_date),
            'end_date': str(self.end_date),
            'days_tested': days_in_test,
            'initial_capital': self.initial_capital,
            'final_value': round(final_value, 2),
            'total_return': round(total_return, 2),
            'total_return_pct': round(total_return_pct, 2),
            'max_drawdown_pct': round(max_drawdown, 2),
            'sharpe_ratio': round(sharpe_ratio, 3),
            'closed_trades': closed_trades,
            'winning_trades': winning_trades,
            'win_rate_pct': round(win_rate, 1),
            'avg_r_per_trade': round(avg_r_per_trade, 2),
            'avg_win_r': round(avg_win_r, 2),
            'avg_loss_r': round(avg_loss_r, 2),
            'profit_factor': round(profit_factor, 2),
            'expectancy_r': round(expectancy_r, 3),
            'max_positions': self.max_positions,
            'trades': self.trades,
        }
        return results

    def save_results_to_db(self, results: Dict[str, Any], strategy_name: str = 'momentum', run_name: str = None) -> Optional[str]:
        """
        Save backtest results to backtest_runs and backtest_trades tables.
        Returns run_id on success, None on failure.
        """
        if not self.conn:
            logger.error("Database not connected. Call connect() first.")
            return None

        if results.get('status') != 'OK':
            logger.error(f"Cannot save failed backtest: {results.get('status')}")
            return None

        try:
            cur = self.conn.cursor()

            # Generate run_name if not provided
            if not run_name:
                run_name = f"{strategy_name}_{self.start_date}_to_{self.end_date}"

            # Insert into backtest_runs
            run_query = """
                INSERT INTO backtest_runs (
                    run_name, run_timestamp, strategy_name,
                    date_start, date_end,
                    total_signals, total_trades, winning_trades, losing_trades,
                    win_rate, avg_win_pct, avg_loss_pct,
                    expectancy_per_trade, total_return_pct, max_drawdown_pct,
                    sharpe_annualized, sortino_annualized, profit_factor,
                    notes
                ) VALUES (
                    %s, %s, %s,
                    %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s
                )
                RETURNING run_id
            """

            cur.execute(run_query, (
                run_name, datetime.now(), strategy_name,
                self.start_date, self.end_date,
                len(results.get('trades', [])), results['closed_trades'], results['winning_trades'],
                results['closed_trades'] - results['winning_trades'],
                results['win_rate_pct'], results['avg_win_r'] * 100, results['avg_loss_r'] * 100,
                results['expectancy_r'], results['total_return_pct'], results['max_drawdown_pct'],
                results['sharpe_ratio'], results['sharpe_ratio'],  # sortino = sharpe for now
                results['profit_factor'],
                f"Backtest run {run_name}"
            ))

            run_id = cur.fetchone()[0]

            # Insert trades
            for trade in results.get('trades', []):
                trade_query = """
                    INSERT INTO backtest_trades (
                        run_id, symbol,
                        entry_date, exit_date,
                        entry_price, exit_price,
                        quantity, profit_loss, profit_loss_pct,
                        trade_outcome, exit_reason, holding_days
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """

                outcome = 'win' if trade.get('pnl', 0) > 0 else 'loss'
                holding_days = (trade.get('exit_date') - trade.get('entry_date')).days if 'exit_date' in trade else 0

                cur.execute(trade_query, (
                    run_id, trade['symbol'],
                    trade['entry_date'], trade['exit_date'],
                    trade['entry_price'], trade['exit_price'],
                    trade['shares'], trade['pnl'], trade['return_pct'],
                    outcome, 'manual_exit', holding_days
                ))

            self.conn.commit()
            logger.info(f"Saved backtest run {run_id}: {run_name}")
            return str(run_id)

        except Exception as e:
            self.conn.rollback()
            logger.error(f"Failed to save backtest results: {e}")
            return None
        finally:
            if cur:
                cur.close()


def main():
    """Command-line interface."""
    parser = argparse.ArgumentParser(description='Backtest trading strategy')
    parser.add_argument('--start', required=True, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end', required=True, help='End date (YYYY-MM-DD)')
    parser.add_argument('--capital', type=float, default=100_000.0, help='Initial capital')
    parser.add_argument('--max-positions', type=int, default=12, help='Max positions')
    parser.add_argument('--walk-forward', action='store_true', help='Run walk-forward optimization')
    parser.add_argument('--window-size', type=int, default=252, help='Walk-forward window size (days)')
    parser.add_argument('--verbose', action='store_true', help='Verbose output')

    args = parser.parse_args()

    try:
        start_date = _date.fromisoformat(args.start)
        end_date = _date.fromisoformat(args.end)
    except ValueError:
        logger.error("Invalid date format. Use YYYY-MM-DD")
        return 1

    if args.walk_forward:
        # Walk-forward optimization
        logger.info("WALK-FORWARD OPTIMIZATION")

        window_size = timedelta(days=args.window_size)
        windows = []
        current_start = start_date

        while current_start < end_date:
            window_end = min(current_start + window_size, end_date)
            windows.append((current_start, window_end))
            current_start = window_end + timedelta(days=1)

        logger.info(f"Testing {len(windows)} windows of {args.window_size} days each")

        all_results = []
        for i, (win_start, win_end) in enumerate(windows):
            logger.info(f"Window {i+1}/{len(windows)}: {win_start} to {win_end}")
            bt = Backtester(
                start_date=win_start,
                end_date=win_end,
                initial_capital=args.capital,
                max_positions=args.max_positions,
                verbose=args.verbose,
            )
            result = bt.run()
            all_results.append(result)

            if result['status'] == 'OK':
                logger.info(f"Return: {result['total_return_pct']:+.2f}%, "
                      f"Sharpe: {result['sharpe_ratio']:.3f}, "
                      f"DD: {result['max_drawdown_pct']:.2f}%")

        # Calculate WFE
        sharpe_ratios = [r['sharpe_ratio'] for r in all_results if r['status'] == 'OK']
        if len(sharpe_ratios) >= 2:
            avg_is_sharpe = statistics.mean(sharpe_ratios[:-1])
            avg_oos_sharpe = statistics.mean(sharpe_ratios[-1:])
            wfe = avg_oos_sharpe / avg_is_sharpe if avg_is_sharpe > 0 else 0

            logger.info("WALK-FORWARD EFFICIENCY")
            logger.info(f"In-Sample Average Sharpe: {avg_is_sharpe:.3f}")
            logger.info(f"Out-of-Sample Average Sharpe: {avg_oos_sharpe:.3f}")
            logger.info(f"WFE: {wfe:.3f}")
            if wfe < 0.5:
                logger.warning("WFE < 0.5: Possible curve-fitting detected")
            else:
                logger.info("WFE >= 0.5: Results appear robust")

        return 0
    else:
        # Single backtest
        bt = Backtester(
            start_date=start_date,
            end_date=end_date,
            initial_capital=args.capital,
            max_positions=args.max_positions,
            verbose=args.verbose,
        )
        bt.connect()
        result = bt.run()

        # Save results to database
        if result['status'] == 'OK':
            run_id = bt.save_results_to_db(result)
            if run_id:
                result['run_id'] = run_id

        bt.disconnect()

        logger.info("BACKTEST RESULTS")
        logger.info(json.dumps(result, indent=2, default=str))

        return 0 if result.get('status') == 'OK' else 1


if __name__ == '__main__':
    sys.exit(main())
