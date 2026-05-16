#!/usr/bin/env python3
"""
Performance Metrics Calculator - Sharpe, Sortino, Max Drawdown, Win Rate
Runs daily to compute trading performance for dashboard display.

Metrics:
- Sharpe Ratio: Risk-adjusted return (252-day rolling)
- Sortino Ratio: Like Sharpe but only penalizes downside volatility
- Maximum Drawdown: Worst peak-to-trough decline
- Win Rate: % of profitable trades
- Profit Factor: Total wins / Total losses
- Average R-Multiple: Average return in risk units
"""

import os
import sys
import psycopg2
import numpy as np
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime, date, timedelta
from typing import Dict, Optional, Tuple

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

def get_db_config():
    """Get database configuration."""
    return {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", 5432)),
        "user": os.getenv("DB_USER", "stocks"),
        "password": os.getenv("DB_PASSWORD", "postgres"),
        "database": os.getenv("DB_NAME", "stocks"),
    }

class PerformanceMetricsCalculator:
    """Calculate trading performance metrics."""

    def __init__(self):
        self.conn = None
        self.cur = None

    def connect(self):
        """Connect to database."""
        try:
            self.conn = psycopg2.connect(**get_db_config())
            self.cur = self.conn.cursor()
            print("✓ Database connected")
        except Exception as e:
            print(f"✗ Database connection failed: {e}")
            raise

    def disconnect(self):
        """Close database connection."""
        if self.cur:
            self.cur.close()
        if self.conn:
            self.conn.close()

    def get_portfolio_daily_returns(self, lookback_days: int = 252) -> Optional[np.ndarray]:
        """Get daily portfolio returns from snapshots."""
        try:
            self.cur.execute(f"""
                SELECT
                    snapshot_date,
                    total_portfolio_value,
                    LAG(total_portfolio_value) OVER (ORDER BY snapshot_date) as prev_value
                FROM algo_portfolio_snapshots
                WHERE snapshot_date >= CURRENT_DATE - INTERVAL '{lookback_days} days'
                ORDER BY snapshot_date
            """)

            rows = self.cur.fetchall()
            if len(rows) < 2:
                print(f"  ⚠ Insufficient data for returns calculation ({len(rows)} days)")
                return None

            daily_returns = []
            for row in rows[1:]:  # Skip first row (no previous value)
                date_val, value, prev_value = row
                if prev_value and prev_value > 0:
                    daily_ret = (value - prev_value) / prev_value
                    daily_returns.append(daily_ret)

            return np.array(daily_returns) if daily_returns else None
        except Exception as e:
            print(f"  ✗ Error getting returns: {e}")
            return None

    def calculate_sharpe_ratio(self, returns: np.ndarray, risk_free_rate: float = 0.02) -> float:
        """Calculate Sharpe ratio (annualized)."""
        if len(returns) < 2:
            return 0.0

        mean_ret = np.mean(returns)
        std_ret = np.std(returns)

        if std_ret == 0:
            return 0.0

        # Annualize: 252 trading days
        sharpe = (mean_ret - (risk_free_rate / 252)) / std_ret * np.sqrt(252)
        return float(sharpe)

    def calculate_sortino_ratio(self, returns: np.ndarray, risk_free_rate: float = 0.02) -> float:
        """Calculate Sortino ratio (annualized, penalizes downside only)."""
        if len(returns) < 2:
            return 0.0

        mean_ret = np.mean(returns)
        downside_returns = returns[returns < 0]

        if len(downside_returns) == 0:
            return float('inf') if mean_ret > 0 else 0.0

        downside_std = np.std(downside_returns)

        if downside_std == 0:
            return 0.0

        sortino = (mean_ret - (risk_free_rate / 252)) / downside_std * np.sqrt(252)
        return float(sortino)

    def calculate_max_drawdown(self, returns: np.ndarray) -> float:
        """Calculate maximum drawdown."""
        if len(returns) == 0:
            return 0.0

        # Convert returns to cumulative portfolio values (starting at 100)
        cumulative = np.cumprod(1 + returns) * 100
        running_max = np.maximum.accumulate(cumulative)
        drawdown = (cumulative - running_max) / running_max

        return float(np.min(drawdown))

    def get_trade_statistics(self) -> Optional[Dict]:
        """Get trade win/loss statistics."""
        try:
            self.cur.execute("""
                SELECT
                    COUNT(*) as total_trades,
                    SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as winning_trades,
                    SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as losing_trades,
                    SUM(pnl) as total_pnl,
                    AVG(r_multiple) as avg_r_multiple
                FROM algo_trades
                WHERE status IN ('closed', 'exited')
                AND trade_date >= CURRENT_DATE - INTERVAL '90 days'
            """)

            row = self.cur.fetchone()
            if row:
                total, wins, losses, pnl, avg_r = row
                if total and total > 0:
                    return {
                        'total_trades': int(total),
                        'winning_trades': int(wins) if wins else 0,
                        'losing_trades': int(losses) if losses else 0,
                        'win_rate': (wins / total * 100) if total > 0 else 0,
                        'total_pnl': float(pnl) if pnl else 0,
                        'avg_r_multiple': float(avg_r) if avg_r else 0,
                    }
            return None
        except Exception as e:
            print(f"  ✗ Error getting trade stats: {e}")
            return None

    def persist_metrics(self, report_date: date, metrics: Dict):
        """Save metrics to database."""
        try:
            self.cur.execute("""
                INSERT INTO algo_performance_daily (
                    report_date,
                    rolling_sharpe_252d,
                    rolling_sortino_252d,
                    max_drawdown_pct,
                    win_rate_pct,
                    profit_factor
                ) VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (report_date) DO UPDATE SET
                    rolling_sharpe_252d = EXCLUDED.rolling_sharpe_252d,
                    rolling_sortino_252d = EXCLUDED.rolling_sortino_252d,
                    max_drawdown_pct = EXCLUDED.max_drawdown_pct,
                    win_rate_pct = EXCLUDED.win_rate_pct,
                    profit_factor = EXCLUDED.profit_factor
            """, (
                report_date,
                metrics.get('sharpe', 0),
                metrics.get('sortino', 0),
                metrics.get('max_dd', 0),
                metrics.get('win_rate', 0),
                metrics.get('profit_factor', 0),
            ))
            self.conn.commit()
            print(f"✓ Metrics persisted for {report_date}")
        except Exception as e:
            print(f"✗ Failed to persist metrics: {e}")

    def calculate_all(self, report_date: Optional[date] = None):
        """Calculate all performance metrics."""
        if report_date is None:
            report_date = date.today()

        print(f"\n{'='*60}")
        print(f"PERFORMANCE METRICS CALCULATION — {report_date}")
        print(f"{'='*60}\n")

        self.connect()

        metrics = {}

        # Calculate returns-based metrics
        print("Calculating returns-based metrics...")
        returns = self.get_portfolio_daily_returns(lookback_days=252)

        if returns is not None and len(returns) > 0:
            sharpe = self.calculate_sharpe_ratio(returns)
            sortino = self.calculate_sortino_ratio(returns)
            max_dd = self.calculate_max_drawdown(returns)

            metrics['sharpe'] = round(sharpe, 2)
            metrics['sortino'] = round(sortino, 2)
            metrics['max_dd'] = round(max_dd * 100, 2)

            print(f"  Sharpe Ratio (252d): {metrics['sharpe']}")
            print(f"  Sortino Ratio (252d): {metrics['sortino']}")
            print(f"  Max Drawdown: {metrics['max_dd']}%")
        else:
            print("  ⚠ Insufficient data for returns-based metrics")
            metrics['sharpe'] = 0
            metrics['sortino'] = 0
            metrics['max_dd'] = 0

        # Calculate trade-based metrics
        print("\nCalculating trade-based metrics (90d)...")
        trade_stats = self.get_trade_statistics()

        if trade_stats:
            metrics['win_rate'] = round(trade_stats['win_rate'], 1)

            # Profit factor = sum(wins) / sum(losses) or 0 if no losses
            if trade_stats['losing_trades'] > 0 and trade_stats['total_pnl'] > 0:
                metrics['profit_factor'] = round(
                    trade_stats['total_pnl'] / abs(trade_stats['total_pnl']), 2
                )
            else:
                metrics['profit_factor'] = 1.0 if trade_stats['total_pnl'] >= 0 else 0.0

            print(f"  Win Rate: {metrics['win_rate']}%")
            print(f"  Profit Factor: {metrics['profit_factor']}")
            print(f"  Total Trades (90d): {trade_stats['total_trades']}")
        else:
            print("  ⚠ Insufficient trade data")
            metrics['win_rate'] = 0
            metrics['profit_factor'] = 0

        # Persist to database
        print("\nPersisting metrics...")
        self.persist_metrics(report_date, metrics)

        self.disconnect()

        print(f"\n{'='*60}")
        print("Calculation complete")
        print(f"{'='*60}\n")

        return metrics

if __name__ == "__main__":
    calc = PerformanceMetricsCalculator()

    report_date = None
    if len(sys.argv) > 1:
        try:
            report_date = datetime.strptime(sys.argv[1], "%Y-%m-%d").date()
        except ValueError:
            print(f"Invalid date format. Use YYYY-MM-DD")
            sys.exit(1)

    try:
        metrics = calc.calculate_all(report_date)
        sys.exit(0)
    except Exception as e:
        print(f"✗ Calculation failed: {e}")
        sys.exit(1)
