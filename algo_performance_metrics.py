#!/usr/bin/env python3
"""Calculate performance metrics - Sharpe, Sortino, max drawdown, etc."""

import sys
import json
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

import psycopg2
from psycopg2.extras import RealDictCursor
import numpy as np
from algo_config import DATABASE_CONFIG

def get_performance_metrics():
    """Calculate all performance metrics from closed trades."""
    try:
        conn = psycopg2.connect(
            host=DATABASE_CONFIG['host'],
            port=DATABASE_CONFIG['port'],
            database=DATABASE_CONFIG['database'],
            user=DATABASE_CONFIG['user'],
            password=DATABASE_CONFIG['password']
        )
        
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Get all closed trades with P&L
            cur.execute("""
                SELECT
                    trade_id, symbol, entry_date, exit_date,
                    entry_price, exit_price, entry_quantity,
                    profit_loss_dollars, profit_loss_pct,
                    EXTRACT(DAY FROM exit_date - entry_date) as holding_days
                FROM algo_trades
                WHERE status = 'closed'
                ORDER BY exit_date ASC
            """)
            trades = cur.fetchall()
            
        if not trades:
            return {'error': 'No closed trades found'}
        
        # Extract metrics
        pnls = [float(t['profit_loss_dollars']) for t in trades if t['profit_loss_dollars']]
        pnl_pcts = [float(t['profit_loss_pct']) for t in trades if t['profit_loss_pct']]
        
        # Wins/losses
        wins = sum(1 for p in pnls if p > 0)
        losses = sum(1 for p in pnls if p < 0)
        win_rate = (wins / len(pnls) * 100) if pnls else 0
        
        # Avg win/loss
        avg_win = float(np.mean([p for p in pnls if p > 0])) if wins > 0 else 0
        avg_loss = float(np.mean([p for p in pnls if p < 0])) if losses > 0 else 0
        profit_factor = float(abs(avg_win * wins / (avg_loss * losses)) if losses > 0 else 0)
        
        # Sharpe ratio (assuming 252 trading days, 0% risk-free rate)
        daily_returns = np.array(pnl_pcts) / 100
        std_daily = np.std(daily_returns)
        sharpe = float((np.mean(daily_returns) / std_daily * np.sqrt(252)) if std_daily > 0 else 0)

        # Sortino ratio (only downside volatility)
        downside_returns = np.array([r for r in daily_returns if r < 0])
        downside_vol = np.std(downside_returns) if len(downside_returns) > 0 else 0
        sortino = float((np.mean(daily_returns) / downside_vol * np.sqrt(252)) if downside_vol > 0 else 0)

        # Max drawdown
        cumulative = np.cumprod(1 + daily_returns)
        running_max = np.maximum.accumulate(cumulative)
        drawdown = (cumulative - running_max) / running_max
        max_dd = float(np.min(drawdown) if len(drawdown) > 0 else 0)
        
        # Total P&L
        total_pnl = sum(pnls)
        total_pnl_pct = sum(pnl_pcts)
        
        return {
            'success': True,
            'trade_count': len(trades),
            'wins': wins,
            'losses': losses,
            'win_rate': round(win_rate, 2),
            'avg_win': round(avg_win, 2),
            'avg_loss': round(avg_loss, 2),
            'profit_factor': round(profit_factor, 2),
            'total_pnl': round(total_pnl, 2),
            'total_pnl_pct': round(total_pnl_pct, 2),
            'sharpe_ratio': round(sharpe, 2),
            'sortino_ratio': round(sortino, 2),
            'max_drawdown_pct': round(max_dd * 100, 2),
            'avg_holding_days': round(float(np.mean([t['holding_days'] for t in trades if t['holding_days']])), 1),
        }
    except Exception as e:
        return {'error': str(e)}
    finally:
        if conn:
            conn.close()

if __name__ == '__main__':
    result = get_performance_metrics()
    print(json.dumps(result))
