#!/usr/bin/env python3
"""
Rolling Sharpe Ratio Monitor - Detect system degradation

Calculates rolling Sharpe over 20, 50, 200-day windows.
Alerts when Sharpe drops below thresholds.

Detects:
1. Short-term degradation (20-day drops)
2. Medium-term decline (50-day drops)
3. Long-term deterioration (200-day trend)

Early warning system for when signal quality declines.
"""

try:
    from credential_manager import get_credential_manager
    credential_manager = get_credential_manager()
except ImportError:
    credential_manager = None

import os
import psycopg2
import statistics
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime, date as _date, timedelta
from typing import Dict, List, Tuple, Optional
import logging
import math
from credential_helper import get_db_password, get_db_config

logger = logging.getLogger(__name__)

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "user": os.getenv("DB_USER", "stocks"),
    "password": get_db_password(),
    "database": os.getenv("DB_NAME", "stocks"),
}

# Alert thresholds
SHARPE_ALERT_THRESHOLDS = {
    'critical': 0.5,   # Red alert
    'warning': 0.8,    # Yellow alert
    'healthy': 1.0,    # Green
    'excellent': 1.5,  # Best case
}


class RollingSharpMonitor:
    """Monitor rolling Sharpe ratio and detect degradation."""

    def __init__(self, cur=None):
        self.cur = cur
        self.conn = None

    def connect(self):
        if not self.cur:
            self.conn = psycopg2.connect(**DB_CONFIG)
            self.cur = self.conn.cursor()

    def disconnect(self):
        if self.conn:
            self.cur.close()
            self.conn.close()
            self.cur = self.conn = None

    def get_daily_returns(self, start_date: _date, end_date: _date) -> List[Tuple[_date, float]]:
        """
        Get daily returns (profit_loss_pct for each closed trade).

        Returns list of (date, return_pct) tuples.
        """
        try:
            self.cur.execute(
                """
                SELECT exit_date, profit_loss_pct FROM algo_trades
                WHERE status = 'closed'
                  AND exit_date >= %s
                  AND exit_date <= %s
                ORDER BY exit_date ASC
                """,
                (start_date, end_date),
            )

            returns = []
            for date, pct in self.cur.fetchall():
                if pct is not None:
                    returns.append((date, float(pct) / 100.0))  # Convert to decimal

            return returns

        except Exception as e:
            logger.error(f"Error fetching daily returns: {e}")
            return []

    def calculate_sharpe(self, returns: List[float], periods_per_year: int = 252) -> Optional[float]:
        """
        Calculate Sharpe ratio from returns list.

        Assumes returns are daily. Scales to annual.
        """
        if not returns or len(returns) < 2:
            return None

        mean_return = statistics.mean(returns)
        if len(returns) > 1:
            std_return = statistics.stdev(returns)
        else:
            return None

        if std_return == 0:
            return 0

        # Sharpe = (mean_return * 252) / (std_return * sqrt(252))
        sharpe = (mean_return * periods_per_year) / (std_return * math.sqrt(periods_per_year))

        return sharpe

    def calculate_rolling_sharpe(self, start_date: _date, end_date: _date,
                               window_days: int = 20) -> List[Dict]:
        """
        Calculate rolling Sharpe ratio over window_days.

        Returns:
            List of {
                'date': date,
                'window_days': int,
                'sharpe': float,
                'trades_in_window': int,
                'avg_daily_return': float,
                'std_daily_return': float,
            }
        """
        all_returns = self.get_daily_returns(start_date, end_date)

        if not all_returns:
            return []

        rolling_sharpes = []
        dates = [r[0] for r in all_returns]
        returns = [r[1] for r in all_returns]

        # For each day, calculate Sharpe using past N days
        for i in range(window_days, len(returns)):
            window_returns = returns[i - window_days:i]
            window_date = dates[i - 1]

            if window_returns:
                sharpe = self.calculate_sharpe(window_returns)
                mean_return = statistics.mean(window_returns) if window_returns else 0
                std_return = statistics.stdev(window_returns) if len(window_returns) > 1 else 0

                rolling_sharpes.append({
                    'date': window_date,
                    'window_days': window_days,
                    'sharpe': sharpe if sharpe is not None else 0,
                    'trades_in_window': len(window_returns),
                    'avg_daily_return': mean_return,
                    'std_daily_return': std_return,
                })

        return rolling_sharpes

    def detect_degradation(self, rolling_sharpes: List[Dict]) -> Dict:
        """
        Detect degradation patterns in rolling Sharpe.

        Returns:
            {
                'latest_sharpe': float,
                'trend': 'improving' | 'stable' | 'degrading' | 'critical',
                'alerts': [str],
                'recommendations': [str],
            }
        """
        if not rolling_sharpes:
            return {
                'latest_sharpe': None,
                'trend': 'unknown',
                'alerts': ['Insufficient data'],
                'recommendations': [],
            }

        latest = rolling_sharpes[-1]['sharpe']
        alerts = []
        recommendations = []

        # Determine status
        if latest < SHARPE_ALERT_THRESHOLDS['critical']:
            trend = 'critical'
            alerts.append(f"🔴 CRITICAL: Sharpe {latest:.2f} < {SHARPE_ALERT_THRESHOLDS['critical']}")
            recommendations.append("⚠️ IMMEDIATE ACTION: Review signal quality")
            recommendations.append("   - Check if market regime changed")
            recommendations.append("   - Verify data freshness")
            recommendations.append("   - Consider reducing position size")

        elif latest < SHARPE_ALERT_THRESHOLDS['warning']:
            trend = 'degrading'
            alerts.append(f"🟡 WARNING: Sharpe {latest:.2f} < {SHARPE_ALERT_THRESHOLDS['warning']}")
            recommendations.append("⚠️ Watch closely:")
            recommendations.append("   - Next 3 trades critical")
            recommendations.append("   - If Sharpe drops further, escalate to critical")

        elif latest < SHARPE_ALERT_THRESHOLDS['healthy']:
            trend = 'stable'
            alerts.append(f"🟢 Watch: Sharpe {latest:.2f} (below healthy threshold {SHARPE_ALERT_THRESHOLDS['healthy']})")

        else:
            trend = 'improving'
            alerts.append(f"✓ Healthy: Sharpe {latest:.2f} (above threshold)")

        # Check for recent decline
        if len(rolling_sharpes) >= 5:
            recent_avg = statistics.mean([r['sharpe'] for r in rolling_sharpes[-5:]])
            older_avg = statistics.mean([r['sharpe'] for r in rolling_sharpes[-10:-5]])

            decline_pct = ((older_avg - recent_avg) / older_avg * 100) if older_avg > 0 else 0

            if decline_pct > 20:
                alerts.append(f"⚠️ Recent decline: {decline_pct:.1f}% drop in last 5 periods")

                if trend == 'stable':
                    trend = 'degrading'

        return {
            'latest_sharpe': latest,
            'trend': trend,
            'alerts': alerts,
            'recommendations': recommendations,
        }

    def generate_report(self, days_back: int = 90, window_days: int = 20) -> str:
        """Generate rolling Sharpe report with alerts."""
        start_date = _date.today() - timedelta(days=days_back)
        end_date = _date.today()

        # Calculate rolling Sharpe for multiple windows
        rolling_20 = self.calculate_rolling_sharpe(start_date, end_date, window_days=20)
        rolling_50 = self.calculate_rolling_sharpe(start_date, end_date, window_days=50)
        rolling_200 = self.calculate_rolling_sharpe(start_date, end_date, window_days=200)

        # Detect degradation
        degradation = self.detect_degradation(rolling_20)

        # Build report
        report = f"""
ROLLING SHARPE RATIO MONITORING
{'='*70}
Period: {days_back} days ({start_date} to {end_date})

LATEST ROLLING SHARPE RATIOS:
  20-day window:  {rolling_20[-1]['sharpe'] if rolling_20 else 'N/A':.2f}  ({rolling_20[-1]['trades_in_window'] if rolling_20 else 0} trades)
  50-day window:  {rolling_50[-1]['sharpe'] if rolling_50 else 'N/A':.2f}  ({rolling_50[-1]['trades_in_window'] if rolling_50 else 0} trades)
  200-day window: {rolling_200[-1]['sharpe'] if rolling_200 else 'N/A':.2f}  ({rolling_200[-1]['trades_in_window'] if rolling_200 else 0} trades)

HEALTH STATUS: {degradation['trend'].upper()}
  Current Sharpe: {degradation['latest_sharpe']:.2f}

ALERTS:
"""

        for alert in degradation['alerts']:
            report += f"  {alert}\n"

        if degradation['recommendations']:
            report += "\nRECOMMENDATIONS:\n"
            for rec in degradation['recommendations']:
                report += f"  {rec}\n"

        # Show trend over time
        if rolling_20:
            report += f"\nRECENT TREND (Last 10 20-day windows):\n"
            for window in rolling_20[-10:]:
                sharpe_bar = "█" * int(max(0, min(10, window['sharpe'] * 5)))
                report += f"  {window['date']}: {sharpe_bar} {window['sharpe']:.2f}\n"

        report += f"\n{'='*70}\n"

        return report


# Standalone usage
if __name__ == '__main__':
    monitor = RollingSharpMonitor()
    monitor.connect()
    try:
        report = monitor.generate_report(days_back=90, window_days=20)
        print(report)
    finally:
        monitor.disconnect()

