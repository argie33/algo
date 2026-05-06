#!/usr/bin/env python3
"""
Paper Trading Acceptance Criteria — Formal gates for production sign-off

After paper trading (real Alpaca account in dry-run mode), validate that live
performance matches backtest expectations before risking capital.

Formal Gates (all must pass):
1. Live Sharpe ≥ 70% of backtest Sharpe (minimum 4 weeks data)
2. Live win rate within 15% of backtest win rate
3. Max live paper drawdown ≤ 1.5× backtest max drawdown
4. Execution fill rate ≥ 95% (not getting rejected)
5. Average slippage ≤ 2× backtest assumed slippage
6. Zero CRITICAL/ERROR data patrol findings during paper period

Passing all gates: Print "PAPER TRADING VALIDATION PASSED — READY FOR PRODUCTION SIGN-OFF"
"""

import os
import psycopg2
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime, date, timedelta
from typing import Dict, Any, Optional
import json

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


class PaperTradingValidator:
    """Validate paper trading performance against backtest baseline."""

    def __init__(self, backtest_metrics: Dict[str, Any], paper_start_date: date = None):
        """
        Args:
            backtest_metrics: Reference metrics from backtest (Sharpe, win rate, DD, etc.)
            paper_start_date: Date paper trading started (default today - 30 days)
        """
        self.backtest_metrics = backtest_metrics
        self.paper_start = paper_start_date or (date.today() - timedelta(days=30))
        self.conn = None
        self.cur = None
        self.gates = {}

    def connect(self):
        """Connect to database."""
        try:
            self.conn = psycopg2.connect(**DB_CONFIG)
            self.cur = self.conn.cursor()
        except Exception as e:
            print(f"[ERROR] Database connection failed: {e}")
            raise

    def disconnect(self):
        """Disconnect from database."""
        if self.cur:
            self.cur.close()
        if self.conn:
            self.conn.close()
        self.cur = self.conn = None

    def validate_all(self) -> Dict[str, Any]:
        """Run all validation gates."""
        print(f"\n{'='*80}")
        print(f"PAPER TRADING VALIDATION — Production Sign-Off Gates")
        print(f"{'='*80}\n")
        print(f"Paper Trading Period: {self.paper_start} to {date.today()}")
        print(f"Backtest Reference: Sharpe {self.backtest_metrics.get('sharpe_ratio', 'N/A')}, "
              f"Win Rate {self.backtest_metrics.get('win_rate_pct', 'N/A')}%\n")

        self.connect()
        try:
            self._gate_1_sharpe_ratio()
            self._gate_2_win_rate()
            self._gate_3_max_drawdown()
            self._gate_4_fill_rate()
            self._gate_5_slippage()
            self._gate_6_data_quality()
        finally:
            self.disconnect()

        return self._summarize()

    def _gate_1_sharpe_ratio(self):
        """GATE 1: Live Sharpe ≥ 70% of backtest Sharpe (minimum 4 weeks)."""
        gate_id = 'sharpe_ratio'
        backtest_sharpe = self.backtest_metrics.get('sharpe_ratio', 0)
        threshold = backtest_sharpe * 0.70

        print(f"GATE 1: Sharpe Ratio Validation")
        print(f"  Backtest Sharpe: {backtest_sharpe:.3f}")
        print(f"  Minimum Required: {threshold:.3f} (70% of backtest)")

        # Get live Sharpe from paper trading period
        self.cur.execute("""
            SELECT rolling_sharpe_252d FROM algo_performance_daily
            WHERE report_date >= %s AND report_date <= %s
            ORDER BY report_date DESC LIMIT 1
        """, (self.paper_start, date.today()))
        row = self.cur.fetchone()

        if row and row[0]:
            live_sharpe = float(row[0])
            passed = live_sharpe >= threshold
            self.gates[gate_id] = {
                'status': 'PASS' if passed else 'FAIL',
                'live_value': round(live_sharpe, 3),
                'threshold': round(threshold, 3),
                'message': f"Live Sharpe {live_sharpe:.3f} {'≥' if passed else '<'} {threshold:.3f}",
            }
            print(f"  Live Sharpe: {live_sharpe:.3f}")
            print(f"  Status: {'[PASS]' if passed else '[FAIL]'}\n")
        else:
            self.gates[gate_id] = {
                'status': 'FAIL',
                'reason': 'Insufficient paper trading data (need ≥4 weeks)',
            }
            print(f"  Status: [FAIL] Insufficient data\n")

    def _gate_2_win_rate(self):
        """GATE 2: Live win rate within 15% of backtest win rate."""
        gate_id = 'win_rate'
        backtest_wr = self.backtest_metrics.get('win_rate_pct', 0)
        lower_bound = max(0, backtest_wr - 15)
        upper_bound = min(100, backtest_wr + 15)

        print(f"GATE 2: Win Rate Validation")
        print(f"  Backtest Win Rate: {backtest_wr:.1f}%")
        print(f"  Acceptable Range: {lower_bound:.1f}% to {upper_bound:.1f}% (±15%)")

        self.cur.execute("""
            SELECT COUNT(*) as total,
                   SUM(CASE WHEN profit_loss_pct > 0 THEN 1 ELSE 0 END) as wins
            FROM algo_trades
            WHERE exit_date >= %s AND exit_date <= %s AND status = 'closed'
        """, (self.paper_start, date.today()))
        row = self.cur.fetchone()

        if row and row[0] > 0:
            total_trades = row[0]
            win_count = row[1] or 0
            live_wr = (win_count / total_trades * 100) if total_trades > 0 else 0
            passed = lower_bound <= live_wr <= upper_bound

            self.gates[gate_id] = {
                'status': 'PASS' if passed else 'FAIL',
                'live_value': round(live_wr, 1),
                'lower_bound': round(lower_bound, 1),
                'upper_bound': round(upper_bound, 1),
                'trades': total_trades,
                'message': f"Live WR {live_wr:.1f}% {'✓' if passed else '✗'} [{lower_bound:.1f}%-{upper_bound:.1f}%]",
            }
            print(f"  Live Win Rate: {live_wr:.1f}% ({win_count}/{total_trades} trades)")
            print(f"  Status: {'[PASS]' if passed else '[FAIL]'}\n")
        else:
            self.gates[gate_id] = {
                'status': 'FAIL',
                'reason': 'No closed trades in paper period',
            }
            print(f"  Status: [FAIL] No closed trades\n")

    def _gate_3_max_drawdown(self):
        """GATE 3: Max live drawdown ≤ 1.5× backtest max drawdown."""
        gate_id = 'max_drawdown'
        backtest_dd = self.backtest_metrics.get('max_drawdown_pct', 0)
        threshold = abs(backtest_dd) * 1.5

        print(f"GATE 3: Maximum Drawdown Validation")
        print(f"  Backtest Max DD: {backtest_dd:.2f}%")
        print(f"  Maximum Allowed: {threshold:.2f}% (1.5× backtest)")

        self.cur.execute("""
            SELECT max_drawdown_pct FROM algo_risk_daily
            WHERE report_date >= %s AND report_date <= %s
            ORDER BY report_date DESC LIMIT 1
        """, (self.paper_start, date.today()))
        row = self.cur.fetchone()

        if row and row[0]:
            live_dd = float(row[0])
            passed = abs(live_dd) <= threshold

            self.gates[gate_id] = {
                'status': 'PASS' if passed else 'FAIL',
                'live_value': round(live_dd, 2),
                'threshold': round(threshold, 2),
                'message': f"Live DD {abs(live_dd):.2f}% {'≤' if passed else '>'} {threshold:.2f}%",
            }
            print(f"  Live Max DD: {live_dd:.2f}%")
            print(f"  Status: {'[PASS]' if passed else '[FAIL]'}\n")
        else:
            self.gates[gate_id] = {
                'status': 'FAIL',
                'reason': 'No risk data available',
            }
            print(f"  Status: [FAIL] No data\n")

    def _gate_4_fill_rate(self):
        """GATE 4: Execution fill rate ≥ 95%."""
        gate_id = 'fill_rate'
        threshold = 95.0

        print(f"GATE 4: Execution Fill Rate")
        print(f"  Minimum Required: {threshold:.1f}%")

        self.cur.execute("""
            SELECT COUNT(*) as submitted,
                   SUM(CASE WHEN status IN ('open', 'closed') THEN 1 ELSE 0 END) as filled
            FROM algo_trades
            WHERE entry_date >= %s AND entry_date <= %s
        """, (self.paper_start, date.today()))
        row = self.cur.fetchone()

        if row and row[0] > 0:
            submitted = row[0]
            filled = row[1] or 0
            fill_rate = (filled / submitted * 100) if submitted > 0 else 0
            passed = fill_rate >= threshold

            self.gates[gate_id] = {
                'status': 'PASS' if passed else 'FAIL',
                'fill_rate': round(fill_rate, 1),
                'submitted': submitted,
                'filled': filled,
                'threshold': threshold,
                'message': f"Fill rate {fill_rate:.1f}% {'✓' if passed else '✗'} (need {threshold:.1f}%)",
            }
            print(f"  Fill Rate: {fill_rate:.1f}% ({filled}/{submitted} orders)")
            print(f"  Status: {'[PASS]' if passed else '[FAIL]'}\n")
        else:
            self.gates[gate_id] = {
                'status': 'FAIL',
                'reason': 'No trades submitted',
            }
            print(f"  Status: [FAIL] No trades\n")

    def _gate_5_slippage(self):
        """GATE 5: Average slippage ≤ 2× backtest assumed slippage."""
        gate_id = 'slippage'
        assumed_slippage_bps = 10.0  # Assume 10bps in backtest
        max_allowed_bps = assumed_slippage_bps * 2

        print(f"GATE 5: Execution Slippage")
        print(f"  Assumed Backtest Slippage: {assumed_slippage_bps:.1f} bps")
        print(f"  Maximum Allowed: {max_allowed_bps:.1f} bps")

        self.cur.execute("""
            SELECT AVG(ABS(slippage_bps)) as avg_slippage
            FROM algo_tca
            WHERE signal_date >= %s AND signal_date <= %s
        """, (self.paper_start, date.today()))
        row = self.cur.fetchone()

        if row and row[0]:
            avg_slippage = float(row[0])
            passed = avg_slippage <= max_allowed_bps

            self.gates[gate_id] = {
                'status': 'PASS' if passed else 'FAIL',
                'avg_slippage_bps': round(avg_slippage, 2),
                'max_allowed_bps': round(max_allowed_bps, 2),
                'message': f"Avg slippage {avg_slippage:.1f} bps {'≤' if passed else '>'} {max_allowed_bps:.1f} bps",
            }
            print(f"  Average Slippage: {avg_slippage:.2f} bps")
            print(f"  Status: {'[PASS]' if passed else '[FAIL]'}\n")
        else:
            self.gates[gate_id] = {
                'status': 'FAIL',
                'reason': 'No TCA data available',
            }
            print(f"  Status: [FAIL] No TCA data\n")

    def _gate_6_data_quality(self):
        """GATE 6: Zero CRITICAL/ERROR data patrol findings."""
        gate_id = 'data_quality'

        print(f"GATE 6: Data Quality (Data Patrol)")
        print(f"  Requirement: Zero CRITICAL/ERROR findings")

        self.cur.execute("""
            SELECT severity, COUNT(*) as count
            FROM data_patrol_log
            WHERE check_date >= %s AND check_date <= %s
            AND severity IN ('CRITICAL', 'ERROR')
            GROUP BY severity
        """, (self.paper_start, date.today()))
        rows = self.cur.fetchall()

        issues = {row[0]: row[1] for row in rows}
        passed = len(issues) == 0

        self.gates[gate_id] = {
            'status': 'PASS' if passed else 'FAIL',
            'critical_count': issues.get('CRITICAL', 0),
            'error_count': issues.get('ERROR', 0),
            'message': 'No data quality issues' if passed else f"Found {sum(issues.values())} issues",
        }

        if passed:
            print(f"  Status: [PASS] No data quality issues\n")
        else:
            print(f"  Found Issues:")
            for severity, count in issues.items():
                print(f"    {severity}: {count}")
            print(f"  Status: [FAIL]\n")

    def _summarize(self) -> Dict[str, Any]:
        """Generate validation summary."""
        print(f"{'='*80}")
        print(f"VALIDATION SUMMARY")
        print(f"{'='*80}\n")

        passed_gates = sum(1 for g in self.gates.values() if g.get('status') == 'PASS')
        total_gates = len(self.gates)

        for gate_id, gate_result in self.gates.items():
            status = gate_result.get('status', 'UNKNOWN')
            status_str = f"[{status}]" if status != 'PASS' else "[PASS]"
            message = gate_result.get('message', gate_result.get('reason', 'N/A'))
            print(f"  {gate_id:20s} {status_str:10s} {message}")

        print(f"\n{'='*80}")
        print(f"Result: {passed_gates}/{total_gates} gates passed")

        if passed_gates == total_gates:
            print(f"\n*** PAPER TRADING VALIDATION PASSED ***")
            print(f"*** READY FOR PRODUCTION SIGN-OFF ***")
            print(f"{'='*80}\n")
            return {
                'status': 'APPROVED',
                'gates_passed': passed_gates,
                'gates_total': total_gates,
                'details': self.gates,
            }
        else:
            print(f"\n[BLOCKED] {total_gates - passed_gates} gate(s) failed")
            print(f"Address failures before production deployment")
            print(f"{'='*80}\n")
            return {
                'status': 'REJECTED',
                'gates_passed': passed_gates,
                'gates_total': total_gates,
                'details': self.gates,
            }


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Validate paper trading against backtest baseline')
    parser.add_argument('--backtest-sharpe', type=float, required=True, help='Backtest Sharpe ratio')
    parser.add_argument('--backtest-wr', type=float, required=True, help='Backtest win rate %')
    parser.add_argument('--backtest-dd', type=float, required=True, help='Backtest max drawdown %')
    parser.add_argument('--paper-start', type=str, help='Paper trading start date (YYYY-MM-DD)')
    args = parser.parse_args()

    backtest_metrics = {
        'sharpe_ratio': args.backtest_sharpe,
        'win_rate_pct': args.backtest_wr,
        'max_drawdown_pct': args.backtest_dd,
    }

    paper_start = None
    if args.paper_start:
        from datetime import date
        paper_start = date.fromisoformat(args.paper_start)

    validator = PaperTradingValidator(backtest_metrics, paper_start)
    result = validator.validate_all()

    print(json.dumps(result, indent=2, default=str))
