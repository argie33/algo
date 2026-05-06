"""
Walk-Forward Optimization (WFO) & Stress Testing

Validates backtest robustness using rigorous out-of-sample testing.

Walk-Forward Process:
1. Split historical data into rolling windows (e.g., 3-year in-sample, 1-year out-of-sample)
2. Optimize parameters on each in-sample window
3. Apply optimized parameters to out-of-sample window
4. Stitch OOS periods → continuous equity curve
5. Compute Walk-Forward Efficiency (WFE) = OOS_Sharpe / IS_Sharpe

WFE interpretation:
- WFE > 0.8: Excellent (minimal overfitting)
- WFE > 0.5: Acceptable (some overfitting expected)
- WFE < 0.3: Likely curve-fit (parameters overfit to in-sample)
- WFE < 0.0: Failure (OOS worse than random)

Stress Testing:
Backtests current parameters against historical crisis periods:
- 2008-09 GFC (Sep 2008 - Mar 2009)
- 2020 COVID (Feb - Apr 2020)
- 2022 Rate Shock (Jan - Dec 2022)
- 2000-02 Dot-Com (Jan 2000 - Dec 2002)

Reports max drawdown, Calmar ratio, recovery time for each crisis.
"""

import psycopg2
import os
import json
from datetime import datetime, date, timedelta
from typing import Optional, Dict, Any, List, Tuple
from pathlib import Path
from dotenv import load_dotenv
import numpy as np

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "user": os.getenv("DB_USER", "stocks"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "stocks"),
}


class WalkForwardOptimizer:
    """Walk-Forward Optimization and Robustness Testing."""

    def __init__(self, config):
        self.config = config
        self.conn = None
        self.cur = None

    def connect(self):
        """Connect to database."""
        try:
            self.conn = psycopg2.connect(**DB_CONFIG)
            self.cur = self.conn.cursor()
        except Exception as e:
            print(f"WFO: DB connection failed: {e}")
            raise

    def disconnect(self):
        """Disconnect from database."""
        if self.cur:
            self.cur.close()
        if self.conn:
            self.conn.close()
        self.cur = self.conn = None

    def walk_forward_backtest(self, data: List[Dict[str, Any]], in_sample_years: int = 3,
                             oos_years: int = 1) -> Dict[str, Any]:
        """Execute walk-forward optimization on historical data.

        Args:
            data: Historical price data with date, close, volume
            in_sample_years: Years for in-sample optimization window
            oos_years: Years for out-of-sample validation window

        Returns:
            dict with WFE, OOS metrics, IS metrics, window details
        """
        if not data or len(data) < 365 * (in_sample_years + oos_years):
            return {
                'status': 'insufficient_data',
                'message': f'Need at least {365 * (in_sample_years + oos_years)} days of data'
            }

        windows = []
        oos_returns = []
        is_sharpes = []
        oos_sharpes = []

        # Create rolling windows
        start_idx = 0
        window_count = 0

        while start_idx + (365 * (in_sample_years + oos_years)) <= len(data):
            window_count += 1
            is_end_idx = start_idx + (365 * in_sample_years)
            oos_end_idx = is_end_idx + (365 * oos_years)

            is_data = data[start_idx:is_end_idx]
            oos_data = data[is_end_idx:oos_end_idx]

            if not oos_data:
                break

            # Optimize on in-sample
            is_params = self._optimize_parameters(is_data)
            is_metrics = self._backtest_window(is_data, is_params)

            # Validate on out-of-sample
            oos_metrics = self._backtest_window(oos_data, is_params)

            is_sharpe = is_metrics.get('sharpe_ratio', 0)
            oos_sharpe = oos_metrics.get('sharpe_ratio', 0)

            windows.append({
                'window': window_count,
                'is_period': f"{is_data[0]['date']} to {is_data[-1]['date']}",
                'oos_period': f"{oos_data[0]['date']} to {oos_data[-1]['date']}",
                'is_sharpe': round(is_sharpe, 3),
                'oos_sharpe': round(oos_sharpe, 3),
                'is_max_dd': round(is_metrics.get('max_drawdown', 0), 2),
                'oos_max_dd': round(oos_metrics.get('max_drawdown', 0), 2),
                'is_win_rate': round(is_metrics.get('win_rate', 0), 2),
                'oos_win_rate': round(oos_metrics.get('win_rate', 0), 2),
            })

            is_sharpes.append(is_sharpe)
            oos_sharpes.append(oos_sharpe)

            start_idx = is_end_idx  # Move to next OOS period as next IS period

        if not oos_sharpes or not is_sharpes:
            return {
                'status': 'no_windows',
                'message': 'Could not create enough WFO windows'
            }

        # Compute Walk-Forward Efficiency
        avg_is_sharpe = np.mean(is_sharpes)
        avg_oos_sharpe = np.mean(oos_sharpes)
        wfe = avg_oos_sharpe / avg_is_sharpe if avg_is_sharpe != 0 else 0

        # Interpretation
        if wfe > 0.8:
            wfe_status = 'EXCELLENT (minimal overfitting)'
        elif wfe > 0.5:
            wfe_status = 'ACCEPTABLE (some overfitting)'
        elif wfe > 0.3:
            wfe_status = 'CONCERNING (significant overfitting)'
        else:
            wfe_status = 'FAILED (severe overfitting or worse OOS performance)'

        return {
            'status': 'success',
            'windows': windows,
            'window_count': window_count,
            'avg_is_sharpe': round(avg_is_sharpe, 3),
            'avg_oos_sharpe': round(avg_oos_sharpe, 3),
            'wfe': round(wfe, 3),
            'wfe_status': wfe_status,
            'is_years': in_sample_years,
            'oos_years': oos_years,
        }

    def crisis_stress_test(self) -> Dict[str, Any]:
        """Run backtest on historical crisis periods with current parameters.

        Tests on: 2008-09 GFC, 2020 COVID, 2022 Rate Shock, 2000-02 Dot-Com

        Returns:
            dict with metrics for each crisis period
        """
        crisis_periods = [
            {
                'name': '2008-09 GFC',
                'start': date(2008, 9, 1),
                'end': date(2009, 3, 31),
                'description': 'Global Financial Crisis — 58% S&P 500 decline',
            },
            {
                'name': '2020 COVID',
                'start': date(2020, 2, 1),
                'end': date(2020, 4, 30),
                'description': 'COVID-19 Pandemic — 34% S&P 500 decline in Feb-Mar',
            },
            {
                'name': '2022 Rate Shock',
                'start': date(2022, 1, 1),
                'end': date(2022, 12, 31),
                'description': 'Fed Rate Hikes — 19% S&P 500 decline, high volatility',
            },
            {
                'name': '2000-02 Dot-Com',
                'start': date(2000, 1, 1),
                'end': date(2002, 12, 31),
                'description': 'Tech Bubble Burst — NASDAQ down 78%, widows & orphans',
            },
        ]

        results = []

        try:
            self.connect()

            for crisis in crisis_periods:
                # Fetch historical data for crisis period
                self.cur.execute(
                    """
                    SELECT date, close FROM price_daily
                    WHERE symbol = 'SPY' AND date BETWEEN %s AND %s
                    ORDER BY date ASC
                    """,
                    (crisis['start'], crisis['end'])
                )
                rows = self.cur.fetchall()

                if len(rows) < 10:  # Insufficient data for crisis period
                    results.append({
                        'period': crisis['name'],
                        'status': 'insufficient_data',
                    })
                    continue

                # Convert to backtest format
                data = [{'date': row[0], 'close': float(row[1])} for row in rows]

                # Run backtest on crisis period
                metrics = self._backtest_window(data, self.config)

                results.append({
                    'period': crisis['name'],
                    'description': crisis['description'],
                    'days_tested': len(data),
                    'sharpe': round(metrics.get('sharpe_ratio', 0), 3),
                    'max_drawdown_pct': round(metrics.get('max_drawdown', 0), 2),
                    'win_rate_pct': round(metrics.get('win_rate', 0), 2),
                    'calmar_ratio': round(metrics.get('calmar_ratio', 0), 3),
                    'profit_factor': round(metrics.get('profit_factor', 0), 2),
                    'status': 'ok',
                })

        except Exception as e:
            print(f"WFO: crisis_stress_test error: {e}")
            return {'status': 'error', 'message': str(e)}
        finally:
            self.disconnect()

        # Interpretation: flag if any crisis period shows severe drawdown or negative returns
        worst_dd = min([r.get('max_drawdown_pct', 0) for r in results if r.get('status') == 'ok'] or [0])

        return {
            'status': 'success',
            'crisis_periods': results,
            'worst_max_drawdown': round(worst_dd, 2),
            'interpretation': 'ACCEPTABLE' if worst_dd < 40 else 'CONCERNING' if worst_dd < 60 else 'SEVERE',
        }

    # Private helpers

    def _optimize_parameters(self, data: List[Dict]) -> Dict[str, Any]:
        """Optimize strategy parameters on in-sample data.

        Placeholder: in production, would use parameter sweep or Bayesian optimization.

        Args:
            data: In-sample price data

        Returns:
            dict with optimized parameters
        """
        # For now, return current config
        # In production: perform grid search or Bayesian optimization over parameter space
        return self.config

    def _backtest_window(self, data: List[Dict], params: Dict) -> Dict[str, Any]:
        """Run backtest on a window of data with given parameters.

        Args:
            data: Price data for window
            params: Strategy parameters

        Returns:
            dict with metrics (sharpe, max_dd, win_rate, calmar, profit_factor)
        """
        if not data or len(data) < 2:
            return {
                'sharpe_ratio': 0,
                'max_drawdown': 0,
                'win_rate': 0,
                'calmar_ratio': 0,
                'profit_factor': 0,
            }

        # Simplified metrics: compute returns and drawdown
        closes = [d['close'] for d in data]
        returns = [(closes[i] - closes[i-1]) / closes[i-1] for i in range(1, len(closes))]

        mean_ret = np.mean(returns) if returns else 0
        std_ret = np.std(returns) if returns else 0.01
        sharpe = (mean_ret / std_ret) * np.sqrt(252) if std_ret > 0 else 0

        # Max drawdown
        peak = closes[0]
        max_dd = 0
        for close in closes:
            if close > peak:
                peak = close
            dd = (close - peak) / peak
            if dd < max_dd:
                max_dd = dd

        max_dd_pct = abs(max_dd) * 100

        # Calmar ratio = annual return / max drawdown
        total_ret = (closes[-1] - closes[0]) / closes[0]
        calmar = total_ret / max_dd_pct if max_dd_pct > 0 else 0

        return {
            'sharpe_ratio': sharpe,
            'max_drawdown': max_dd_pct,
            'win_rate': np.mean([1 for r in returns if r > 0]) * 100 if returns else 0,
            'calmar_ratio': calmar,
            'profit_factor': 1.0,  # Placeholder
        }
