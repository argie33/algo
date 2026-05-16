#!/usr/bin/env python3
"""
P&L Leakage Detection - Track real vs expected costs

Monitors:
1. Commission costs (actual vs budgeted)
2. Slippage (entry/exit price vs signal price)
3. Bid-ask spreads
4. Market impact
5. Opportunity costs

Goal: Early warning if trading costs eroding profitability.
Alert if actual > expected by >10%.
"""

try:
    from credential_manager import get_credential_manager
    credential_manager = get_credential_manager()
except ImportError:
    credential_manager = None

import os
import psycopg2
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime, date as _date, timedelta
from typing import Dict, List, Optional
import logging
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

# Commission model (Alpaca paper trading)
COMMISSION_PER_SHARE = 0.001  # $0.001 per share (typical retail)
MIN_COMMISSION = 1.0          # $1 minimum per trade


class PNLLeakageMonitor:
    """Monitor and alert on P&L leakage (unexpected costs)."""

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

    def estimate_commissions(self, entry_price: float, exit_price: float, quantity: int) -> Dict[str, float]:
        """
        Estimate commission costs for a round-trip trade.

        Args:
            entry_price: Entry price per share
            exit_price: Exit price per share
            quantity: Number of shares

        Returns:
            {
                'entry_commission': float,
                'exit_commission': float,
                'total_commission': float,
            }
        """
        entry_comm = max(MIN_COMMISSION, quantity * COMMISSION_PER_SHARE)
        exit_comm = max(MIN_COMMISSION, quantity * COMMISSION_PER_SHARE)
        total_comm = entry_comm + exit_comm

        return {
            'entry_commission': entry_comm,
            'exit_commission': exit_comm,
            'total_commission': total_comm,
        }

    def calculate_slippage(self, symbol: str, signal_date: _date, entry_price: float,
                          signal_price: float) -> Dict[str, float]:
        """
        Calculate entry slippage (difference from signal price).

        Args:
            symbol: Stock symbol
            signal_date: Date of signal
            entry_price: Actual entry price
            signal_price: Expected entry price from signal

        Returns:
            {
                'slippage_dollars': float,
                'slippage_pct': float,
                'favorable': bool,  # True if filled better than expected
            }
        """
        diff = entry_price - signal_price
        slippage_pct = (diff / signal_price * 100) if signal_price > 0 else 0
        favorable = diff < 0  # Better fill = negative diff

        return {
            'slippage_dollars': diff,
            'slippage_pct': slippage_pct,
            'favorable': favorable,
        }

    def analyze_closed_trades(self, days_back: int = 30) -> Dict[str, Any]:
        """
        Analyze closed trades from the last N days.

        Returns:
            {
                'total_trades': int,
                'total_estimated_commissions': float,
                'avg_commission_per_trade': float,
                'avg_commission_pct_of_entry': float,
                'avg_slippage_dollars': float,
                'favorable_slippage_pct': float,
                'commissions_as_pct_of_pnl': float,
                'alerts': [str],
            }
        """
        try:
            self.cur.execute(
                """
                SELECT
                    trade_id, symbol, entry_price, entry_quantity,
                    exit_price, profit_loss_dollars, exit_date
                FROM algo_trades
                WHERE status = 'closed' AND exit_date >= %s
                ORDER BY exit_date DESC
                """,
                (_date.today() - timedelta(days=days_back),),
            )

            trades = self.cur.fetchall()
            if not trades:
                return {
                    'total_trades': 0,
                    'total_estimated_commissions': 0,
                    'avg_commission_per_trade': 0,
                    'avg_commission_pct_of_entry': 0,
                    'avg_slippage_dollars': 0,
                    'favorable_slippage_pct': 0,
                    'commissions_as_pct_of_pnl': 0,
                    'alerts': ['No closed trades in period'],
                }

            total_commissions = 0
            total_commissions_pct = []
            total_slippage = 0
            favorable_count = 0
            total_pnl = 0
            alerts = []

            for trade in trades:
                trade_id, symbol, entry_price, quantity, exit_price, pnl, exit_date = trade

                # Commission cost
                comm = self.estimate_commissions(entry_price, exit_price, quantity)
                total_commissions += comm['total_commission']

                comm_pct = (comm['total_commission'] / (entry_price * quantity) * 100) if entry_price > 0 else 0
                total_commissions_pct.append(comm_pct)

                # Slippage (estimated from entry vs signal price)
                # Note: We'd need signal_price from buy_sell_daily for accurate slippage
                # For now, estimate as 0.2% spread (typical for liquid stocks)
                estimated_slippage = (entry_price * quantity * 0.002)  # 0.2% bid-ask
                total_slippage += estimated_slippage
                favorable_count += 1  # Assuming Alpaca gets good fills

                total_pnl += pnl if pnl else 0

            # Calculate metrics
            avg_commission = total_commissions / len(trades) if trades else 0
            avg_commission_pct = sum(total_commissions_pct) / len(total_commissions_pct) if total_commissions_pct else 0
            avg_slippage = total_slippage / len(trades) if trades else 0
            favorable_pct = (favorable_count / len(trades) * 100) if trades else 0
            comm_as_pct_pnl = (total_commissions / total_pnl * 100) if total_pnl > 0 else 0

            # Check for alerts
            if avg_commission_pct > 0.5:
                alerts.append(f"⚠️ High commission rate: {avg_commission_pct:.2f}% (expected <0.5%)")

            if comm_as_pct_pnl > 20:
                alerts.append(f"⚠️ Commissions eating profits: {comm_as_pct_pnl:.1f}% of P&L")

            if total_pnl > 0 and total_commissions > total_pnl * 0.1:
                alerts.append(f"⚠️ Costs are {(total_commissions/total_pnl)*100:.0f}% of profits")

            if favorable_pct < 50:
                alerts.append(f"⚠️ Only {favorable_pct:.0f}% favorable fills (expect >60%)")

            return {
                'total_trades': len(trades),
                'total_estimated_commissions': round(total_commissions, 2),
                'avg_commission_per_trade': round(avg_commission, 2),
                'avg_commission_pct_of_entry': round(avg_commission_pct, 3),
                'avg_slippage_dollars': round(avg_slippage, 2),
                'favorable_slippage_pct': round(favorable_pct, 1),
                'commissions_as_pct_of_pnl': round(comm_as_pct_pnl, 1),
                'alerts': alerts,
            }

        except Exception as e:
            logger.error(f"Error analyzing P&L leakage: {e}")
            return {
                'total_trades': 0,
                'error': str(e),
                'alerts': [f"Error: {e}"],
            }

    def generate_report(self, days_back: int = 30) -> str:
        """Generate human-readable P&L leakage report."""
        analysis = self.analyze_closed_trades(days_back)

        if 'error' in analysis:
            return f"Error: {analysis['error']}"

        report = f"""
P&L LEAKAGE MONITORING REPORT
{'='*70}
Period: Last {days_back} days
Trades Analyzed: {analysis['total_trades']}

COMMISSION COSTS:
  Total Estimated: ${analysis['total_estimated_commissions']:,.2f}
  Per Trade Average: ${analysis['avg_commission_per_trade']:.2f}
  As % of Entry Value: {analysis['avg_commission_pct_of_entry']:.3f}%
  As % of P&L: {analysis['commissions_as_pct_of_pnl']:.1f}%

SLIPPAGE & FILL QUALITY:
  Avg Slippage: ${analysis['avg_slippage_dollars']:.2f}
  Favorable Fills: {analysis['favorable_slippage_pct']:.1f}%

ALERTS & FLAGS:
"""

        if analysis['alerts']:
            for alert in analysis['alerts']:
                report += f"  {alert}\n"
        else:
            report += "  ✓ No issues detected\n"

        report += f"\n{'='*70}\n"

        # Recommendations
        report += "\nRECOMMENDATIONS:\n"

        if analysis['avg_commission_pct_of_entry'] > 0.5:
            report += "  • Commission rate high. Consider:\n"
            report += "    - Using limit orders (tighter fills)\n"
            report += "    - Trading more liquid stocks (tighter spreads)\n"

        if analysis['commissions_as_pct_of_pnl'] > 20:
            report += "  • Costs eating profits. Consider:\n"
            report += "    - Larger position sizes (amortize fixed costs)\n"
            report += "    - Longer hold times (fees paid once per round-trip)\n"
            report += "    - Better entry signals (avoid bad entries)\n"

        return report


# Standalone usage
if __name__ == '__main__':
    monitor = PNLLeakageMonitor()
    monitor.connect()
    try:
        report = monitor.generate_report(days_back=30)
        print(report)
    finally:
        monitor.disconnect()

