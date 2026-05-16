#!/usr/bin/env python3
"""
Performance Analysis — Compare Backtest vs Live Trading Results

Compares historical backtest results against actual live paper trading results.
Calculates key metrics:
  - Sharpe Ratio
  - Maximum Drawdown
  - Calmar Ratio
  - Win Rate
  - Profit Factor
  - Expectancy per trade
  - Return
  - Trade duration averages

USAGE:
    python3 algo_performance_analysis.py
    # Generates PERFORMANCE_ANALYSIS_REPORT.md
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
from datetime import datetime, date as _date
from decimal import Decimal
import math

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

def _get_db_config():
    """Lazy-load DB config at runtime instead of module import time."""
    return {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "user": os.getenv("DB_USER", "stocks"),
    "password": credential_manager.get_db_credentials()["password"],
    "database": os.getenv("DB_NAME", "stocks"),
    }


class PerformanceAnalyzer:
    """Analyze backtest vs live trading performance."""

    def __init__(self):
        self.conn = None
        self.cur = None

    def connect(self):
        self.conn = psycopg2.connect(**_get_db_config())
        self.cur = self.conn.cursor()

    def disconnect(self):
        if self.cur:
            self.cur.close()
        if self.conn:
            self.conn.close()

    def get_live_trades(self):
        """Fetch all closed trades from algo_trades (paper trading)."""
        self.cur.execute("""
            SELECT
                trade_id, symbol, signal_date, trade_date, entry_time,
                entry_price, entry_quantity, exit_date, exit_price,
                profit_loss_dollars, profit_loss_pct, trade_duration_days,
                exit_r_multiple, status, execution_mode
            FROM algo_trades
            WHERE status = 'closed' AND exit_date IS NOT NULL
            ORDER BY exit_date ASC
        """)
        trades = []
        for row in self.cur.fetchall():
            trades.append({
                'trade_id': row[0],
                'symbol': row[1],
                'signal_date': row[2],
                'trade_date': row[3],
                'entry_time': row[4],
                'entry_price': float(row[5]),
                'entry_quantity': row[6],
                'exit_date': row[7],
                'exit_price': float(row[8]),
                'pnl_dollars': float(row[9]) if row[9] else 0,
                'pnl_pct': float(row[10]) if row[10] else 0,
                'duration_days': row[11],
                'exit_r_multiple': float(row[12]) if row[12] else None,
                'status': row[13],
                'execution_mode': row[14],
            })
        return trades

    def calculate_metrics(self, trades, initial_capital=100_000):
        """Calculate performance metrics."""
        if not trades:
            return None

        # Sort by exit date
        trades = sorted(trades, key=lambda t: t['exit_date'])

        # 1. Basic stats
        total_trades = len(trades)
        winning_trades = [t for t in trades if t['pnl_dollars'] > 0]
        losing_trades = [t for t in trades if t['pnl_dollars'] < 0]
        breakeven_trades = [t for t in trades if t['pnl_dollars'] == 0]

        win_count = len(winning_trades)
        loss_count = len(losing_trades)
        win_rate = (win_count / total_trades * 100) if total_trades > 0 else 0

        # 2. Profit Factor
        gross_profit = sum(t['pnl_dollars'] for t in winning_trades)
        gross_loss = abs(sum(t['pnl_dollars'] for t in losing_trades))
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else 0

        # 3. Total P&L
        total_pnl = sum(t['pnl_dollars'] for t in trades)
        total_return_pct = (total_pnl / initial_capital) * 100

        # 4. Sharpe Ratio (using daily returns)
        equity_curve = [initial_capital]
        current_equity = initial_capital
        for trade in trades:
            current_equity += trade['pnl_dollars']
            equity_curve.append(current_equity)

        daily_returns = []
        for i in range(1, len(equity_curve)):
            ret = (equity_curve[i] - equity_curve[i-1]) / equity_curve[i-1]
            if ret != 0:  # Only include non-zero returns
                daily_returns.append(ret)

        if daily_returns:
            mean_return = statistics.mean(daily_returns)
            std_return = statistics.stdev(daily_returns) if len(daily_returns) > 1 else 0
            sharpe = (mean_return / std_return * math.sqrt(252)) if std_return > 0 else 0
        else:
            sharpe = 0

        # 5. Maximum Drawdown
        peak = initial_capital
        max_drawdown = 0
        max_drawdown_pct = 0
        for value in equity_curve:
            if value > peak:
                peak = value
            drawdown = peak - value
            drawdown_pct = (drawdown / peak * 100) if peak > 0 else 0
            if drawdown > max_drawdown:
                max_drawdown = drawdown
                max_drawdown_pct = drawdown_pct

        # 6. Calmar Ratio
        calmar = (total_return_pct / max_drawdown_pct) if max_drawdown_pct > 0 else 0

        # 7. Average win/loss
        avg_win = (gross_profit / win_count) if win_count > 0 else 0
        avg_loss = (gross_loss / loss_count) if loss_count > 0 else 0
        avg_win_pct = statistics.mean([t['pnl_pct'] for t in winning_trades]) if winning_trades else 0
        avg_loss_pct = statistics.mean([t['pnl_pct'] for t in losing_trades]) if losing_trades else 0

        # 8. Expectancy (avg P&L per trade)
        expectancy = total_pnl / total_trades if total_trades > 0 else 0
        expectancy_pct = statistics.mean([t['pnl_pct'] for t in trades]) if trades else 0

        # 9. Average hold time
        avg_hold_days = statistics.mean([t['duration_days'] for t in trades if t['duration_days']]) if trades else 0

        # 10. R-multiple statistics
        r_multiples = [t['exit_r_multiple'] for t in trades if t['exit_r_multiple'] is not None]
        avg_r_multiple = statistics.mean(r_multiples) if r_multiples else None
        median_r_multiple = statistics.median(r_multiples) if r_multiples else None

        return {
            'total_trades': total_trades,
            'win_count': win_count,
            'loss_count': loss_count,
            'breakeven_count': len(breakeven_trades),
            'win_rate': win_rate,
            'gross_profit': gross_profit,
            'gross_loss': gross_loss,
            'profit_factor': profit_factor,
            'total_pnl': total_pnl,
            'total_return_pct': total_return_pct,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'avg_win_pct': avg_win_pct,
            'avg_loss_pct': avg_loss_pct,
            'expectancy': expectancy,
            'expectancy_pct': expectancy_pct,
            'sharpe_ratio': sharpe,
            'max_drawdown_dollars': max_drawdown,
            'max_drawdown_pct': max_drawdown_pct,
            'calmar_ratio': calmar,
            'avg_hold_days': avg_hold_days,
            'avg_r_multiple': avg_r_multiple,
            'median_r_multiple': median_r_multiple,
            'trades': trades,
            'equity_curve': equity_curve,
        }

    def generate_report(self, metrics, output_file='PERFORMANCE_ANALYSIS_REPORT.md'):
        """Generate markdown report."""
        if not metrics:
            report = "# Performance Analysis Report\n\n**Status:** No closed trades found in algo_trades table.\n"
            with open(output_file, 'w') as f:
                f.write(report)
            print(f"Report written to {output_file}")
            return

        report = f"""# Performance Analysis Report

**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
**Data Source:** Live Paper Trading (algo_trades table)

---

## Summary Statistics

| Metric | Value |
|--------|-------|
| Total Trades | {metrics['total_trades']} |
| Winning Trades | {metrics['win_count']} |
| Losing Trades | {metrics['loss_count']} |
| Breakeven Trades | {metrics['breakeven_count']} |
| Win Rate | {metrics['win_rate']:.2f}% |
| **Sharpe Ratio** | **{metrics['sharpe_ratio']:.2f}** |
| **Max Drawdown** | **{metrics['max_drawdown_pct']:.2f}%** (${metrics['max_drawdown_dollars']:,.0f}) |
| **Calmar Ratio** | **{metrics['calmar_ratio']:.2f}** |
| **Total Return** | **{metrics['total_return_pct']:.2f}%** (${metrics['total_pnl']:,.0f}) |
| **Profit Factor** | **{metrics['profit_factor']:.2f}x** |

---

## Profitability Analysis

| Metric | Value |
|--------|-------|
| Gross Profit | ${metrics['gross_profit']:,.0f} |
| Gross Loss | ${metrics['gross_loss']:,.0f} |
| Average Win | ${metrics['avg_win']:,.0f} (+{metrics['avg_win_pct']:.2f}%) |
| Average Loss | ${metrics['avg_loss']:,.0f} ({metrics['avg_loss_pct']:.2f}%) |
| **Expectancy per Trade** | **${metrics['expectancy']:,.0f}** ({metrics['expectancy_pct']:.2f}%) |

---

## Trade Quality Metrics

| Metric | Value |
|--------|-------|
| Average Hold Time | {metrics['avg_hold_days']:.1f} days |
| Average R-Multiple | {metrics['avg_r_multiple']:.2f}x if metrics['avg_r_multiple'] else 'N/A' |
| Median R-Multiple | {metrics['median_r_multiple']:.2f}x if metrics['median_r_multiple'] else 'N/A' |

---

## Interpretation

### Sharpe Ratio ({metrics['sharpe_ratio']:.2f})
- **Industry Standard:** > 1.0 is good, > 2.0 is excellent
- **Your Result:** {'[OK] Above 1.0 (acceptable)' if metrics['sharpe_ratio'] > 1.0 else '[!] Below 1.0 (improvement needed)'}
- **Action:** Monitor for consistency; Sharpe < 1.0 means high volatility relative to returns

### Max Drawdown ({metrics['max_drawdown_pct']:.2f}%)
- **Industry Standard:** < 20% is good, < 10% is excellent
- **Your Result:** {'[OK] Below 20%' if metrics['max_drawdown_pct'] < 20 else '[!] Above 20% (risk management review)'}
- **Action:** Consider tighter position sizing or additional circuit breakers

### Win Rate ({metrics['win_rate']:.2f}%)
- **Industry Standard:** 50%+ is acceptable, 55%+ is good
- **Your Result:** {'[OK] Above 50%' if metrics['win_rate'] >= 50 else '[!] Below 50% (margin of safety concerns)'}
- **Action:** {'Good win rate; focus on avg win > avg loss' if metrics['win_rate'] >= 50 else 'Improve signal quality or filters'}

### Profit Factor ({metrics['profit_factor']:.2f}x)
- **Industry Standard:** > 1.5x is good, > 2.0x is excellent
- **Your Result:** {'[OK] Above 1.5x (solid)' if metrics['profit_factor'] > 1.5 else '[!] Below 1.5x (losers too big relative to winners)'}
- **Action:** Reduce average loss size OR increase average win size

### Calmar Ratio ({metrics['calmar_ratio']:.2f})
- **Industry Standard:** > 0.5 is acceptable, > 1.0 is good, > 2.0 is excellent
- **Your Result:** {'[OK] Above 1.0 (good risk-adjusted returns)' if metrics['calmar_ratio'] > 1.0 else '[!] Below 1.0 (drawdown eating returns)'}
- **Action:** {'Good balance of returns and drawdown' if metrics['calmar_ratio'] > 1.0 else 'Reduce drawdown via position sizing'}

---

## Trade-by-Trade Breakdown (Last 20 Trades)

"""

        # Table of recent trades
        report += "| Date | Symbol | Entry | Exit | P&L | % | Days | R-Multiple |\n"
        report += "|------|--------|-------|------|-----|-----|------|------------|\n"

        recent_trades = metrics['trades'][-20:] if len(metrics['trades']) > 20 else metrics['trades']
        for trade in recent_trades:
            report += f"| {trade['exit_date']} | {trade['symbol']} | "
            report += f"${trade['entry_price']:.2f} | ${trade['exit_price']:.2f} | "
            report += f"${trade['pnl_dollars']:,.0f} | {trade['pnl_pct']:.2f}% | "
            report += f"{trade['duration_days']} | "
            if trade['exit_r_multiple']:
                report += f"{trade['exit_r_multiple']:.2f}x |\n"
            else:
                report += "N/A |\n"

        report += f"""

---

## Key Insights

### Strengths
- {'[OK] Strong Sharpe ratio indicates quality risk-adjusted returns' if metrics['sharpe_ratio'] > 1.0 else '[!] Sharpe ratio suggests room for improvement'}
- {'[OK] Acceptable max drawdown shows good risk management' if metrics['max_drawdown_pct'] < 20 else '[!] Max drawdown needs attention'}
- {'[OK] Win rate above 50% provides margin of safety' if metrics['win_rate'] >= 50 else '[!] Win rate needs improvement'}

### Areas to Improve
- Expectancy: Focus on increasing average win size or reducing average loss size
- Consistency: Track rolling Sharpe ratio to detect periods of degradation
- Signal quality: Consider Phase 2 enhancements (Minervini, RS > 70, volume confirmation)

---

## Backtest vs Live (When Available)

When you run `python3 algo_backtest.py --start 2026-01-01 --end {_date.today()}`,
compare these metrics:
- Sharpe ratio gap (live vs backtest) should be < 10%
- Win rate gap should be < 5%
- If live performs significantly better: backtest may be too optimistic
- If live performs significantly worse: signals may have degraded or overfitted

---

## Recommendations

1. **Immediate:** Monitor Sharpe ratio weekly; set alert if drops below 0.5
2. **This Week:** Run full backtest and compare to live results
3. **Next Week:** Implement Phase 2 signal enhancements (Minervini + RS > 70)
4. **Monthly:** Review Profit Factor and adjust position sizing if needed

---

**Last Updated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""

        with open(output_file, 'w') as f:
            f.write(report)

        print(f"\n[OK] Report written to {output_file}")
        return report

    def run(self):
        """Main execution."""
        print("[*] Analyzing live trading performance...")
        self.connect()
        try:
            trades = self.get_live_trades()
            print(f"  -> Found {len(trades)} closed trades")

            if trades:
                metrics = self.calculate_metrics(trades)
                self.generate_report(metrics)

                # Print summary to console
                print(f"\n[SUMMARY] Live Trading Metrics:")
                print(f"   Total Trades: {metrics['total_trades']}")
                print(f"   Win Rate: {metrics['win_rate']:.2f}%")
                print(f"   Sharpe Ratio: {metrics['sharpe_ratio']:.2f}")
                print(f"   Max Drawdown: {metrics['max_drawdown_pct']:.2f}%")
                print(f"   Total Return: {metrics['total_return_pct']:.2f}%")
                print(f"   Profit Factor: {metrics['profit_factor']:.2f}x")
            else:
                print("  [WARN] No closed trades found")

        finally:
            self.disconnect()


if __name__ == '__main__':
    analyzer = PerformanceAnalyzer()
    analyzer.run()
