#!/usr/bin/env python3
"""
Backtest CLI Script
Runs a strategy backtest against historical signals and stores results in backtest_runs table.

Usage:
  python backtest.py --strategy swing --date-start 2022-01-01 --date-end 2024-12-31 --name "Swing baseline"
  python backtest.py --strategy range --params '{"min_range_height": 100}' --name "Range 1%+ only"
  python backtest.py --strategy mean_reversion --min-confluence 3 --name "Mean rev high quality"
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import psycopg2
from dotenv import load_dotenv

# Load environment
env_path = Path(__file__).parent / '.env.local'
if env_path.exists():
    load_dotenv(env_path)

# Database config
DB_SECRET_ARN = os.environ.get("DB_SECRET_ARN")
DB_HOST = os.environ.get("DB_HOST", "localhost")
DB_PORT = int(os.environ.get("DB_PORT", 5432))
DB_USER = os.environ.get("DB_USER", "stocks")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
DB_NAME = os.environ.get("DB_NAME", "stocks")

if DB_SECRET_ARN:
    try:
        import boto3
        sm_client = boto3.client("secretsmanager")
        secret_resp = sm_client.get_secret_value(SecretId=DB_SECRET_ARN)
        creds = json.loads(secret_resp["SecretString"])
        DB_USER = creds["username"]
        DB_PASSWORD = creds["password"]
        DB_HOST = creds["host"]
        DB_PORT = int(creds.get("port", 5432))
        DB_NAME = creds["dbname"]
    except:
        pass

def get_db_connection():
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        dbname=DB_NAME
    )

def create_backtest_tables():
    """Create backtest result tables if they don't exist"""
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        # Create backtest_runs table
        runs_table = """
            CREATE TABLE IF NOT EXISTS backtest_runs (
                run_id BIGSERIAL PRIMARY KEY,
                run_name VARCHAR(200) NOT NULL,
                run_timestamp TIMESTAMP DEFAULT NOW(),
                strategy_name VARCHAR(50),
                strategy_method VARCHAR(50),
                parameters JSONB,
                date_start DATE,
                date_end DATE,
                total_signals INTEGER,
                winning_trades INTEGER,
                losing_trades INTEGER,
                scratch_trades INTEGER,
                win_rate REAL,
                avg_win_pct REAL,
                avg_loss_pct REAL,
                win_loss_ratio REAL,
                expectancy_per_trade REAL,
                total_return_pct REAL,
                max_drawdown_pct REAL,
                sharpe REAL,
                sortino REAL,
                profit_factor REAL,
                equity_curve JSONB,
                notes TEXT,
                status VARCHAR(20) DEFAULT 'completed'
            );

            CREATE INDEX IF NOT EXISTS idx_backtest_runs_strategy ON backtest_runs(strategy_name, run_timestamp DESC);
            CREATE INDEX IF NOT EXISTS idx_backtest_runs_timestamp ON backtest_runs(run_timestamp DESC);
        """

        # Create backtest_trades table
        trades_table = """
            CREATE TABLE IF NOT EXISTS backtest_trades (
                trade_id BIGSERIAL PRIMARY KEY,
                run_id BIGINT REFERENCES backtest_runs(run_id) ON DELETE CASCADE,
                symbol VARCHAR(20),
                signal_date DATE,
                exit_date DATE,
                signal_type VARCHAR(50),
                entry_price REAL,
                exit_price REAL,
                return_pct REAL,
                outcome VARCHAR(10),
                exit_reason VARCHAR(30),
                mfe_pct REAL,
                mae_pct REAL,
                days_held INTEGER
            );

            CREATE INDEX IF NOT EXISTS idx_backtest_trades_run ON backtest_trades(run_id);
        """

        cur.execute(runs_table)
        cur.execute(trades_table)
        conn.commit()
        print("✅ Backtest tables ready")

    except Exception as e:
        print(f"⚠️ Error creating backtest tables: {e}")
    finally:
        cur.close()
        conn.close()

def backtest_swing_strategy(date_start, date_end, **kwargs):
    """Backtest swing breakout strategy"""
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        # Get signals for this period
        q = """
            SELECT
                bsd.symbol, bsd.date, bsd.signal,
                bsd.buylevel as entry_price, bsd.stoplevel as stop_level,
                bsd.profit_target_25pct as target_price,
                bsd.signal_type
            FROM buy_sell_daily bsd
            WHERE bsd.date >= %s AND bsd.date <= %s
                AND bsd.signal IN ('BUY', 'SELL')
            ORDER BY bsd.symbol, bsd.date
        """
        cur.execute(q, (date_start, date_end))
        signals = cur.fetchall()

        # Replay each signal against subsequent price data
        results = []
        for symbol, signal_date, signal, entry_price, stop_level, target_price, signal_type in signals:
            # Get next 60 days of price data
            price_q = """
                SELECT date, close, high, low
                FROM price_daily
                WHERE symbol = %s AND date > %s AND date <= DATE(%s) + INTERVAL '60 days'
                ORDER BY date
            """
            cur.execute(price_q, (symbol, signal_date, signal_date))
            prices = cur.fetchall()

            if not prices:
                continue

            outcome = replay_signal(signal, entry_price, stop_level, target_price, prices)
            if outcome:
                results.append(outcome)

        # Calculate KPIs
        kpis = calculate_kpis(results)
        return kpis, results

    finally:
        cur.close()
        conn.close()

def backtest_range_strategy(date_start, date_end, **kwargs):
    """Backtest range trading strategy"""
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        # Get signals
        q = """
            SELECT
                rs.symbol, rs.date, rs.signal,
                rs.entry_price, rs.stop_level, rs.target_2,
                rs.signal_type
            FROM range_signals_daily rs
            WHERE rs.date >= %s AND rs.date <= %s
                AND rs.signal IN ('BUY', 'SELL')
            ORDER BY rs.symbol, rs.date
        """
        cur.execute(q, (date_start, date_end))
        signals = cur.fetchall()

        results = []
        for symbol, signal_date, signal, entry_price, stop_level, target_price, signal_type in signals:
            price_q = """
                SELECT date, close, high, low
                FROM price_daily
                WHERE symbol = %s AND date > %s AND date <= DATE(%s) + INTERVAL '60 days'
                ORDER BY date
            """
            cur.execute(price_q, (symbol, signal_date, signal_date))
            prices = cur.fetchall()

            if not prices:
                continue

            outcome = replay_signal(signal, entry_price, stop_level, target_price, prices)
            if outcome:
                results.append(outcome)

        kpis = calculate_kpis(results)
        return kpis, results

    finally:
        cur.close()
        conn.close()

def backtest_mean_reversion_strategy(date_start, date_end, min_confluence=0, **kwargs):
    """Backtest mean reversion strategy"""
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        # Get signals
        q = """
            SELECT
                mrs.symbol, mrs.date, mrs.signal,
                mrs.entry_price, mrs.stop_level, mrs.target_estimate,
                mrs.signal_type, mrs.confluence_score
            FROM mean_reversion_signals_daily mrs
            WHERE mrs.date >= %s AND mrs.date <= %s
                AND mrs.signal = 'BUY'
                AND mrs.confluence_score >= %s
            ORDER BY mrs.symbol, mrs.date
        """
        cur.execute(q, (date_start, date_end, min_confluence))
        signals = cur.fetchall()

        results = []
        for symbol, signal_date, signal, entry_price, stop_level, target_price, signal_type, confluence in signals:
            price_q = """
                SELECT date, close, high, low
                FROM price_daily
                WHERE symbol = %s AND date > %s AND date <= DATE(%s) + INTERVAL '20 days'
                ORDER BY date
            """
            cur.execute(price_q, (symbol, signal_date, signal_date))
            prices = cur.fetchall()

            if not prices:
                continue

            outcome = replay_signal_with_exit(symbol, entry_price, stop_level, prices, strategy='mean_reversion')
            if outcome:
                results.append(outcome)

        kpis = calculate_kpis(results)
        return kpis, results

    finally:
        cur.close()
        conn.close()

def replay_signal(signal_direction, entry_price, stop_level, target_price, prices):
    """Replay a signal and determine outcome"""
    if not entry_price or not stop_level or not prices:
        return None

    entry_date = prices[0][0]
    exit_date = None
    exit_price = None
    outcome = None
    mfe = 0
    mae = 0
    days_held = 0

    for i, (date, close, high, low) in enumerate(prices):
        days_held = i

        if signal_direction == 'BUY':
            # Check for stop hit
            if low <= stop_level:
                exit_date = date
                exit_price = stop_level
                outcome = 'LOSS'
                mae = ((stop_level - entry_price) / entry_price) * -100
                break

            # Check for target hit
            if high >= target_price:
                exit_date = date
                exit_price = target_price
                outcome = 'WIN'
                mfe = ((target_price - entry_price) / entry_price) * 100
                break

            # Track MFE/MAE
            mfe = max(mfe, ((high - entry_price) / entry_price) * 100)
            mae = min(mae, ((low - entry_price) / entry_price) * 100)

        elif signal_direction == 'SELL':
            # Check for stop hit
            if high >= stop_level:
                exit_date = date
                exit_price = stop_level
                outcome = 'LOSS'
                mae = ((stop_level - entry_price) / entry_price) * 100
                break

            # Check for target hit
            if low <= target_price:
                exit_date = date
                exit_price = target_price
                outcome = 'WIN'
                mfe = ((entry_price - target_price) / entry_price) * 100
                break

            # Track MFE/MAE
            mfe = max(mfe, ((entry_price - low) / entry_price) * 100)
            mae = min(mae, ((entry_price - high) / entry_price) * 100)

    if exit_date is None:
        # Trade didn't close, use last price
        exit_date = prices[-1][0]
        exit_price = prices[-1][1]
        outcome = 'OPEN'

    return_pct = ((exit_price - entry_price) / entry_price) * 100

    return {
        'entry_date': entry_date,
        'exit_date': exit_date,
        'entry_price': entry_price,
        'exit_price': exit_price,
        'return_pct': return_pct,
        'outcome': outcome,
        'mfe_pct': mfe,
        'mae_pct': mae,
        'days_held': days_held
    }

def replay_signal_with_exit(symbol, entry_price, stop_level, prices, strategy='mean_reversion'):
    """Replay mean reversion signal with exit on 5 SMA cross"""
    if not entry_price or not stop_level or not prices:
        return None

    conn = get_db_connection()
    cur = conn.cursor()

    entry_date = prices[0][0]
    exit_date = None
    exit_price = None
    outcome = None
    mfe = 0
    mae = 0
    days_held = 0

    # Compute 5 SMA on prices (need more history)
    sma5_q = """
        SELECT date, close
        FROM price_daily
        WHERE symbol = %s AND date <= %s
        ORDER BY date DESC
        LIMIT 100
    """
    cur.execute(sma5_q, (symbol, entry_date))
    hist_prices = cur.fetchall()

    # Check for exit signal (close above 5 SMA)
    for i, (date, close, high, low) in enumerate(prices):
        days_held = i

        # Check for stop hit (hard stop)
        if low <= stop_level:
            exit_date = date
            exit_price = stop_level
            outcome = 'LOSS'
            mae = ((stop_level - entry_price) / entry_price) * -100
            break

        # For mean reversion, exit on 5 SMA cross (simplified - just check if price > entry + 2%)
        if close > entry_price * 1.02:
            exit_date = date
            exit_price = close
            outcome = 'WIN'
            mfe = ((close - entry_price) / entry_price) * 100
            break

        # Track MFE/MAE
        mfe = max(mfe, ((high - entry_price) / entry_price) * 100)
        mae = min(mae, ((low - entry_price) / entry_price) * 100)

    cur.close()
    conn.close()

    if exit_date is None:
        # Trade didn't close
        exit_date = prices[-1][0]
        exit_price = prices[-1][1]
        outcome = 'OPEN'

    return_pct = ((exit_price - entry_price) / entry_price) * 100

    return {
        'entry_date': entry_date,
        'exit_date': exit_date,
        'entry_price': entry_price,
        'exit_price': exit_price,
        'return_pct': return_pct,
        'outcome': outcome,
        'mfe_pct': mfe,
        'mae_pct': mae,
        'days_held': days_held
    }

def calculate_kpis(trades):
    """Calculate performance KPIs from trades"""
    if not trades:
        return {}

    df = pd.DataFrame(trades)

    wins = df[df['return_pct'] > 0]
    losses = df[df['return_pct'] < 0]
    scratches = df[df['return_pct'] == 0]

    win_count = len(wins)
    loss_count = len(losses)
    scratch_count = len(scratches)
    total_count = len(df)

    win_rate = (win_count / total_count * 100) if total_count > 0 else 0
    avg_win = wins['return_pct'].mean() if len(wins) > 0 else 0
    avg_loss = losses['return_pct'].mean() if len(losses) > 0 else 0
    win_loss_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else 0

    total_return = df['return_pct'].sum()
    expectancy = (win_rate / 100 * avg_win) + ((1 - win_rate / 100) * avg_loss)

    gross_wins = wins['return_pct'].sum() if len(wins) > 0 else 0
    gross_losses = abs(losses['return_pct'].sum()) if len(losses) > 0 else 0
    profit_factor = gross_wins / gross_losses if gross_losses != 0 else 0

    # Max drawdown
    cumulative_returns = (1 + df['return_pct'] / 100).cumprod()
    running_max = cumulative_returns.expanding().max()
    drawdown = (cumulative_returns - running_max) / running_max
    max_drawdown_pct = drawdown.min() * 100

    # Sharpe ratio (assuming 252 trading days, 0% risk-free rate)
    daily_returns = df['return_pct'] / df['days_held'].replace(0, 1)
    sharpe = (daily_returns.mean() / daily_returns.std() * np.sqrt(252)) if daily_returns.std() != 0 else 0

    # Sortino ratio (downside deviation)
    downside_returns = daily_returns[daily_returns < 0]
    downside_std = downside_returns.std()
    sortino = (daily_returns.mean() / downside_std * np.sqrt(252)) if downside_std != 0 else 0

    return {
        'total_signals': total_count,
        'winning_trades': win_count,
        'losing_trades': loss_count,
        'scratch_trades': scratch_count,
        'win_rate': win_rate,
        'avg_win_pct': avg_win,
        'avg_loss_pct': avg_loss,
        'win_loss_ratio': win_loss_ratio,
        'expectancy_per_trade': expectancy,
        'total_return_pct': total_return,
        'max_drawdown_pct': max_drawdown_pct,
        'sharpe': sharpe,
        'sortino': sortino,
        'profit_factor': profit_factor,
        'equity_curve': build_equity_curve(df)
    }

def build_equity_curve(trades_df):
    """Build equity curve from trades"""
    cumulative = (1 + trades_df['return_pct'] / 100).cumprod() * 100

    return [
        {
            'date': trades_df.iloc[i]['exit_date'].isoformat(),
            'equity': cumulative.iloc[i]
        }
        for i in range(len(trades_df))
    ]

def store_backtest_results(run_name, strategy_name, strategy_method, parameters, kpis, results, date_start, date_end):
    """Store backtest results in database"""
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        insert_q = """
            INSERT INTO backtest_runs (
                run_name, strategy_name, strategy_method, parameters,
                date_start, date_end,
                total_signals, winning_trades, losing_trades, scratch_trades,
                win_rate, avg_win_pct, avg_loss_pct, win_loss_ratio,
                expectancy_per_trade, total_return_pct, max_drawdown_pct,
                sharpe, sortino, profit_factor, equity_curve, status
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING run_id
        """

        cur.execute(insert_q, (
            run_name, strategy_name, strategy_method, json.dumps(parameters),
            date_start, date_end,
            kpis.get('total_signals', 0),
            kpis.get('winning_trades', 0),
            kpis.get('losing_trades', 0),
            kpis.get('scratch_trades', 0),
            kpis.get('win_rate', 0),
            kpis.get('avg_win_pct', 0),
            kpis.get('avg_loss_pct', 0),
            kpis.get('win_loss_ratio', 0),
            kpis.get('expectancy_per_trade', 0),
            kpis.get('total_return_pct', 0),
            kpis.get('max_drawdown_pct', 0),
            kpis.get('sharpe', 0),
            kpis.get('sortino', 0),
            kpis.get('profit_factor', 0),
            json.dumps(kpis.get('equity_curve', [])),
            'completed'
        ))

        run_id = cur.fetchone()[0]

        # Store individual trades
        for trade in results:
            trade_q = """
                INSERT INTO backtest_trades (
                    run_id, entry_date, exit_date, entry_price, exit_price,
                    return_pct, outcome, mfe_pct, mae_pct, days_held
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            cur.execute(trade_q, (
                run_id,
                trade['entry_date'],
                trade['exit_date'],
                trade['entry_price'],
                trade['exit_price'],
                trade['return_pct'],
                trade['outcome'],
                trade['mfe_pct'],
                trade['mae_pct'],
                trade['days_held']
            ))

        conn.commit()
        print(f"✅ Backtest results stored. Run ID: {run_id}")
        print(f"Win rate: {kpis.get('win_rate', 0):.1f}% | Expectancy: {kpis.get('expectancy_per_trade', 0):.3f} | Sharpe: {kpis.get('sharpe', 0):.2f}")

        return run_id

    finally:
        cur.close()
        conn.close()

def main():
    parser = argparse.ArgumentParser(description='Run strategy backtest')
    parser.add_argument('--strategy', required=True, choices=['swing', 'range', 'mean_reversion'], help='Strategy to backtest')
    parser.add_argument('--date-start', required=True, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--date-end', required=True, help='End date (YYYY-MM-DD)')
    parser.add_argument('--name', required=True, help='Run name for tracking')
    parser.add_argument('--params', type=str, help='JSON parameters')
    parser.add_argument('--min-confluence', type=int, default=0, help='Min confluence for mean reversion')
    parser.add_argument('--method', type=str, help='Strategy method override')

    args = parser.parse_args()

    # Create tables if they don't exist
    create_backtest_tables()

    params = json.loads(args.params) if args.params else {}
    strategy_method = args.method or f"{args.strategy}_baseline"

    # Run backtest
    if args.strategy == 'swing':
        kpis, results = backtest_swing_strategy(args.date_start, args.date_end, **params)
    elif args.strategy == 'range':
        kpis, results = backtest_range_strategy(args.date_start, args.date_end, **params)
    else:  # mean_reversion
        kpis, results = backtest_mean_reversion_strategy(
            args.date_start, args.date_end,
            min_confluence=args.min_confluence,
            **params
        )

    # Store results
    run_id = store_backtest_results(
        args.name,
        args.strategy,
        strategy_method,
        params,
        kpis,
        results,
        args.date_start,
        args.date_end
    )

if __name__ == '__main__':
    main()
