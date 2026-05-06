"""
Live Performance Metrics — Compute Sharpe, win rate, expectancy, max drawdown.

Institutional traders measure performance in real-time against backtested metrics.
This module validates live performance against backtest baselines and detects drift.

Metrics computed:
- Rolling Sharpe ratio (252-day annualized)
- Win rate and average R-multiple (last 50 closed trades)
- Expectancy (E = (WR × Avg Win R) - (LR × Avg Loss R))
- Maximum drawdown from peak portfolio value
- Live vs. backtest comparison
"""

import psycopg2
from datetime import datetime, date, timedelta
from typing import Optional, Dict, Any
import os
import json
from dotenv import load_dotenv
from pathlib import Path
import numpy as np

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)


class LivePerformance:
    """Compute live performance metrics for institutional comparison."""

    def __init__(self, config):
        self.config = config
        self.conn = None
        self.cur = None

        self.db_host = os.getenv('DB_HOST', 'localhost')
        self.db_port = int(os.getenv('DB_PORT', 5432))
        self.db_user = os.getenv('DB_USER', 'stocks')
        self.db_password = os.getenv('DB_PASSWORD', '')
        self.db_name = os.getenv('DB_NAME', 'stocks')

    def connect(self):
        """Connect to database."""
        try:
            self.conn = psycopg2.connect(
                host=self.db_host,
                port=self.db_port,
                user=self.db_user,
                password=self.db_password,
                database=self.db_name,
            )
            self.cur = self.conn.cursor()
        except Exception as e:
            print(f"Performance: DB connection failed: {e}")
            raise

    def disconnect(self):
        """Disconnect from database."""
        if self.cur:
            self.cur.close()
        if self.conn:
            self.conn.close()
        self.cur = self.conn = None

    def rolling_sharpe(self, lookback_days: int = 252) -> Optional[float]:
        """Compute rolling Sharpe ratio from daily portfolio returns.

        Args:
            lookback_days: Days to look back (default 252 = 1 year)

        Returns:
            Annualized Sharpe ratio or None if insufficient data
        """
        try:
            # Create fresh connection for this metric
            conn = psycopg2.connect(
                host=self.db_host,
                port=self.db_port,
                user=self.db_user,
                password=self.db_password,
                database=self.db_name,
            )
            cur = conn.cursor()

            # Fetch daily returns from portfolio snapshots
            cur.execute(
                """
                SELECT snapshot_date, total_portfolio_value FROM algo_portfolio_snapshots
                WHERE snapshot_date >= CURRENT_DATE - INTERVAL '%d days'
                ORDER BY snapshot_date ASC
                """ % lookback_days,
            )
            rows = cur.fetchall()
            cur.close()
            conn.close()

            if len(rows) < 30:  # Need at least 30 days to estimate Sharpe
                return None

            # Compute daily returns
            values = [float(row[1]) for row in rows]
            daily_returns = []
            for i in range(1, len(values)):
                ret = (values[i] - values[i-1]) / values[i-1]
                daily_returns.append(ret)

            if not daily_returns:
                return None

            # Annualized Sharpe (assume 252 trading days, 0% risk-free rate)
            mean_return = np.mean(daily_returns)
            std_return = np.std(daily_returns)

            if std_return == 0:
                return None

            daily_sharpe = mean_return / std_return
            annualized_sharpe = daily_sharpe * np.sqrt(252)

            return round(annualized_sharpe, 4)
        except Exception as e:
            print(f"Performance: rolling_sharpe failed: {e}")
            return None

    def win_rate(self, lookback_trades: int = 50) -> Optional[Dict[str, float]]:
        """Compute win rate and average R-multiple from closed trades.

        Args:
            lookback_trades: Number of recent closed trades to analyze

        Returns:
            dict with win_rate_pct, avg_win_r, avg_loss_r, win_count, loss_count
        """
        try:
            # Create fresh connection for this metric
            conn = psycopg2.connect(
                host=self.db_host,
                port=self.db_port,
                user=self.db_user,
                password=self.db_password,
                database=self.db_name,
            )
            cur = conn.cursor()

            cur.execute(
                """
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN profit_loss_pct > 0 THEN 1 ELSE 0 END) as win_count,
                    SUM(CASE WHEN profit_loss_pct <= 0 THEN 1 ELSE 0 END) as loss_count,
                    AVG(CASE WHEN profit_loss_pct > 0 THEN profit_loss_pct ELSE NULL END) as avg_win_pct,
                    AVG(CASE WHEN profit_loss_pct <= 0 THEN profit_loss_pct ELSE NULL END) as avg_loss_pct
                FROM (
                    SELECT profit_loss_pct FROM algo_trades
                    WHERE status = 'closed' AND exit_date >= CURRENT_DATE - INTERVAL '365 days'
                    ORDER BY exit_date DESC NULLS LAST
                    LIMIT %s
                ) closed_trades
                """,
                (lookback_trades,)
            )
            row = cur.fetchone()
            cur.close()
            conn.close()

            if not row or row[0] == 0:
                return None

            total, win_count, loss_count, avg_win_pct, avg_loss_pct = row
            win_count = win_count or 0
            loss_count = loss_count or 0
            avg_win_pct = float(avg_win_pct or 0)
            avg_loss_pct = float(avg_loss_pct or 0)

            win_rate_pct = (win_count / total * 100) if total > 0 else 0

            # Convert % to R-multiples using avg risk per trade (~1%)
            # Rough approximation: 1% gain ≈ 1R, 1% loss ≈ 1R
            avg_win_r = avg_win_pct / 1.0 if avg_win_pct != 0 else 0
            avg_loss_r = abs(avg_loss_pct) / 1.0 if avg_loss_pct != 0 else 0

            return {
                'win_rate_pct': round(win_rate_pct, 2),
                'win_count': int(win_count),
                'loss_count': int(loss_count),
                'avg_win_pct': round(avg_win_pct, 3),
                'avg_loss_pct': round(avg_loss_pct, 3),
                'avg_win_r': round(avg_win_r, 3),
                'avg_loss_r': round(avg_loss_r, 3),
            }
        except Exception as e:
            print(f"Performance: win_rate failed: {e}")
            return None

    def expectancy(self, lookback_trades: int = 50) -> Optional[float]:
        """Compute expectancy: E = (WR × Avg Win R) - (LR × Avg Loss R).

        Args:
            lookback_trades: Number of trades for calculation

        Returns:
            Expectancy in R-multiples
        """
        try:
            wr = self.win_rate(lookback_trades)
            if not wr:
                return None

            win_rate = wr['win_rate_pct'] / 100.0
            loss_rate = 1.0 - win_rate
            avg_win_r = wr['avg_win_r']
            avg_loss_r = wr['avg_loss_r']

            expectancy = (win_rate * avg_win_r) - (loss_rate * avg_loss_r)
            return round(expectancy, 4)
        except Exception as e:
            print(f"Performance: expectancy failed: {e}")
            return None

    def max_drawdown(self) -> Optional[float]:
        """Compute maximum drawdown from peak portfolio value.

        Returns:
            Max drawdown as percentage (e.g., -15.5 = 15.5% down from peak)
        """
        try:
            # Create fresh connection for this metric
            conn = psycopg2.connect(
                host=self.db_host,
                port=self.db_port,
                user=self.db_user,
                password=self.db_password,
                database=self.db_name,
            )
            cur = conn.cursor()

            # Get portfolio values over the last 252 days
            cur.execute(
                """
                SELECT snapshot_date, total_portfolio_value FROM algo_portfolio_snapshots
                WHERE snapshot_date >= CURRENT_DATE - INTERVAL '365 days'
                ORDER BY snapshot_date ASC
                """
            )
            rows = cur.fetchall()
            cur.close()
            conn.close()

            if len(rows) < 2:
                return None

            values = [float(row[1]) for row in rows]
            peak = values[0]
            max_dd = 0.0

            for value in values:
                if value > peak:
                    peak = value
                dd = (value - peak) / peak * 100
                if dd < max_dd:
                    max_dd = dd

            return round(max_dd, 2)
        except Exception as e:
            print(f"Performance: max_drawdown failed: {e}")
            return None

    def backtest_vs_live_comparison(self) -> Optional[Dict[str, Any]]:
        """Compare live metrics to backtest reference metrics.

        Returns:
            dict with live/backtest Sharpe, win rate, etc. and ratio
        """
        try:
            # Load backtest reference metrics
            ref_file = Path(__file__).parent / 'tests' / 'backtest' / 'reference_metrics.json'
            if not ref_file.exists():
                print(f"Performance: Reference metrics not found at {ref_file}")
                return None

            with open(ref_file, 'r') as f:
                backtest_metrics = json.load(f)

            # Compute live metrics
            live_sharpe = self.rolling_sharpe(252)
            live_wr = self.win_rate(50)
            live_expectancy = self.expectancy(50)
            live_max_dd = self.max_drawdown()

            if not all([live_sharpe, live_wr, live_max_dd]):
                return None

            backtest_sharpe = backtest_metrics.get('sharpe_ratio')
            backtest_wr = backtest_metrics.get('win_rate_pct')

            return {
                'live_sharpe': live_sharpe,
                'backtest_sharpe': backtest_sharpe,
                'sharpe_ratio': live_sharpe / backtest_sharpe if backtest_sharpe else None,
                'live_win_rate': live_wr['win_rate_pct'],
                'backtest_win_rate': backtest_wr,
                'win_rate_ratio': live_wr['win_rate_pct'] / backtest_wr if backtest_wr else None,
                'live_expectancy': live_expectancy,
                'live_max_dd': live_max_dd,
                'backtest_max_dd': backtest_metrics.get('max_drawdown_pct'),
            }
        except Exception as e:
            print(f"Performance: backtest_vs_live_comparison failed: {e}")
            return None

    def generate_daily_report(self, report_date: Optional[date] = None) -> Dict[str, Any]:
        """Generate comprehensive daily performance report.

        Args:
            report_date: Date to report on (default today)

        Returns:
            dict with all metrics for the day
        """
        try:
            if not report_date:
                report_date = date.today()

            # Compute all metrics (each handles its own connection)
            sharpe = self.rolling_sharpe(252)
            wr = self.win_rate(50)
            expectancy = self.expectancy(50)
            max_dd = self.max_drawdown()
            comparison = self.backtest_vs_live_comparison()

            result = {
                'report_date': report_date,
                'generated_at': datetime.now().isoformat(),
                'rolling_sharpe_252d': sharpe,
                'status': 'ok',
            }

            if wr:
                result.update({
                    'win_rate_50t': wr['win_rate_pct'],
                    'avg_win_r_50t': wr['avg_win_r'],
                    'avg_loss_r_50t': wr['avg_loss_r'],
                    'expectancy': expectancy,
                })

            if max_dd:
                result['max_drawdown_pct'] = max_dd

            if comparison:
                result['live_vs_backtest'] = comparison
                # Flag warning if Sharpe drops below 70% of backtest
                sharpe_ratio = comparison.get('sharpe_ratio')
                if sharpe_ratio and sharpe_ratio < 0.7:
                    result['status'] = 'warning'
                    result['warning'] = f"Live Sharpe ({sharpe:.2f}) below 70% of backtest ({comparison['backtest_sharpe']:.2f})"

            # Upsert into database with fresh connection (insert or replace if already exists for this date)
            conn = psycopg2.connect(
                host=self.db_host,
                port=self.db_port,
                user=self.db_user,
                password=self.db_password,
                database=self.db_name,
            )
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO algo_performance_daily (
                    report_date, rolling_sharpe_252d, win_rate_50t,
                    avg_win_r, avg_loss_r, expectancy,
                    max_drawdown_pct, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (report_date) DO UPDATE SET
                    rolling_sharpe_252d = EXCLUDED.rolling_sharpe_252d,
                    win_rate_50t = EXCLUDED.win_rate_50t,
                    avg_win_r = EXCLUDED.avg_win_r,
                    avg_loss_r = EXCLUDED.avg_loss_r,
                    expectancy = EXCLUDED.expectancy,
                    max_drawdown_pct = EXCLUDED.max_drawdown_pct
                """,
                (
                    report_date,
                    sharpe,
                    wr['win_rate_pct'] if wr else None,
                    wr['avg_win_r'] if wr else None,
                    wr['avg_loss_r'] if wr else None,
                    expectancy,
                    max_dd,
                )
            )
            conn.commit()
            cur.close()
            conn.close()

            return result

        except Exception as e:
            print(f"Performance: generate_daily_report failed: {e}")
            return {'status': 'error', 'message': str(e)}
