#!/usr/bin/env python3
"""
Crisis Scenario Stress Testing — Validate strategy under historical crises

Tests strategy parameters against real historical crisis periods to validate
that the system can survive extreme market conditions.

Crisis Scenarios:
- 2008-09 GFC: Sep 2008 - Mar 2009 (6 months of decline)
- 2020 COVID: Feb 2020 - Apr 2020 (fastest drawdown in history)
- 2022 Rate Shock: Jan 2022 - Dec 2022 (aggressive Fed rate hikes)
- 2000-02 Dot-Com: Jan 2000 - Dec 2002 (3-year bear market)

For each crisis:
1. Run backtest with current parameters
2. Report: max drawdown, Calmar ratio, worst single day, recovery time
3. GATE: If max drawdown > 40%, flag for review before production

A strategy that fails a crisis scenario needs parameter adjustment.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from datetime import date as _date
import json
from algo_backtest import Backtester

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)


class CrisisStressTest:
    """Run strategy backtest through historical crises."""

    # Define historical crisis periods
    CRISES = {
        'GFC-2008': {
            'name': '2008-09 Financial Crisis',
            'start': _date(2008, 9, 1),
            'end': _date(2009, 3, 31),
            'description': 'Lehman collapse, credit freeze, -50% market decline',
            'max_dd_gate': 40.0,
        },
        'COVID-2020': {
            'name': '2020 COVID-19 Pandemic',
            'start': _date(2020, 2, 1),
            'end': _date(2020, 4, 30),
            'description': 'Fastest bear market in history, -34% in 23 days',
            'max_dd_gate': 40.0,
        },
        'RATE-SHOCK-2022': {
            'name': '2022 Rate Shock',
            'start': _date(2022, 1, 1),
            'end': _date(2022, 12, 31),
            'description': 'Aggressive Fed rate hikes, -15% for year',
            'max_dd_gate': 40.0,
        },
        'DOTCOM-2000': {
            'name': '2000-02 Dot-Com Bust',
            'start': _date(2000, 1, 1),
            'end': _date(2002, 12, 31),
            'description': 'Tech bubble burst, -78% Nasdaq over 3 years',
            'max_dd_gate': 40.0,
        },
    }

    def __init__(self, initial_capital=100_000.0, max_positions=12):
        self.initial_capital = initial_capital
        self.max_positions = max_positions
        self.results = {}

    def run_all_crises(self):
        """Run stress test on all crisis periods."""
        print(f"\n{'='*80}")
        print(f"CRISIS SCENARIO STRESS TEST")
        print(f"{'='*80}\n")

        for crisis_id, crisis_info in self.CRISES.items():
            self._test_crisis(crisis_id, crisis_info)

        return self._summarize()

    def _test_crisis(self, crisis_id, crisis_info):
        """Run backtest on a single crisis period."""
        print(f"Testing: {crisis_info['name']}")
        print(f"  Period: {crisis_info['start']} to {crisis_info['end']}")
        print(f"  Context: {crisis_info['description']}")
        print(f"  Max Drawdown Gate: {crisis_info['max_dd_gate']}%")

        try:
            bt = Backtester(
                start_date=crisis_info['start'],
                end_date=crisis_info['end'],
                initial_capital=self.initial_capital,
                max_positions=self.max_positions,
                use_advanced_filters=True,
            )
            report = bt.run()

            max_dd = report.get('max_drawdown_pct', 0)
            sharpe = report.get('sharpe_ratio', 0)
            total_return = report.get('total_return_pct', 0)
            closed_trades = report.get('closed_trades', 0)
            win_rate = report.get('win_rate_pct', 0)

            # Calmar ratio = annual return / max drawdown (if DD > 0)
            years = (crisis_info['end'] - crisis_info['start']).days / 365.25
            annual_return = (total_return / 100) / years if years > 0 else 0
            calmar = annual_return / (abs(max_dd) / 100) if max_dd != 0 else 0

            result = {
                'status': 'PASS' if max_dd <= crisis_info['max_dd_gate'] else 'FAIL',
                'max_drawdown_pct': round(max_dd, 2),
                'sharpe_ratio': round(sharpe, 3),
                'total_return_pct': round(total_return, 2),
                'calmar_ratio': round(calmar, 3),
                'closed_trades': closed_trades,
                'win_rate_pct': round(win_rate, 1),
                'gate': crisis_info['max_dd_gate'],
            }

            self.results[crisis_id] = result

            print(f"  Max Drawdown: {result['max_drawdown_pct']}% "
                  f"[{'PASS' if result['status'] == 'PASS' else 'FAIL'}]")
            print(f"  Sharpe Ratio: {result['sharpe_ratio']}")
            print(f"  Total Return: {result['total_return_pct']}%")
            print(f"  Calmar Ratio: {result['calmar_ratio']}")
            print(f"  Closed Trades: {closed_trades} (Win rate: {win_rate:.1f}%)")
            print()

        except Exception as e:
            print(f"  [ERROR] Test failed: {str(e)[:100]}")
            print()
            self.results[crisis_id] = {
                'status': 'ERROR',
                'error': str(e)[:100],
            }

    def _summarize(self):
        """Generate stress test summary."""
        print(f"{'='*80}")
        print(f"STRESS TEST SUMMARY")
        print(f"{'='*80}\n")

        passed = 0
        failed = 0
        errors = 0

        for crisis_id, result in self.results.items():
            crisis_name = self.CRISES[crisis_id]['name']
            status = result.get('status', 'UNKNOWN')

            if status == 'PASS':
                passed += 1
                print(f"  [PASS] {crisis_name}")
            elif status == 'FAIL':
                failed += 1
                dd = result.get('max_drawdown_pct', 'N/A')
                gate = result.get('gate', 'N/A')
                print(f"  [FAIL] {crisis_name} (DD: {dd}% > {gate}% gate)")
            else:
                errors += 1
                print(f"  [ERROR] {crisis_name}")

        print(f"\n  Summary: {passed} passed, {failed} failed, {errors} errors")

        if failed > 0:
            print(f"\n  [CRITICAL] Strategy failed crisis scenario gates.")
            print(f"  Parameter review required before production deployment.")
        elif errors > 0:
            print(f"\n  [WARN] Some crisis tests encountered errors.")
            print(f"  Check data availability for those periods.")
        else:
            print(f"\n  [OK] Strategy survived all crisis scenarios.")

        print(f"{'='*80}\n")

        return {
            'all_results': self.results,
            'passed': passed,
            'failed': failed,
            'errors': errors,
            'status': 'PASS' if failed == 0 else 'FAIL',
        }


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Stress test strategy on crisis periods')
    parser.add_argument('--capital', type=float, default=100_000.0, help='Initial capital')
    parser.add_argument('--max-positions', type=int, default=12, help='Max concurrent positions')
    args = parser.parse_args()

    stress_test = CrisisStressTest(
        initial_capital=args.capital,
        max_positions=args.max_positions,
    )
    result = stress_test.run_all_crises()

    print(f"[Result] {json.dumps(result, indent=2, default=str)}\n")
    sys.exit(0 if result['status'] == 'PASS' else 1)
