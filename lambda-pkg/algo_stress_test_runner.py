#!/usr/bin/env python3
"""
Stress Test Runner - Backtest during historical market crashes

Tests system resilience on:
1. 2008 Financial Crisis (Sep 2008 - Mar 2009): -57% SPY drawdown
2. 2020 COVID Crash (Feb 2020 - Mar 2020): -34% SPY drawdown
3. 2022 Bear Market (Jan 2022 - Oct 2022): -26% SPY drawdown

Goal: Verify circuit breakers work and max loss limits hold.
Expected: Win rate drops, but system should still be profitable or break-even.
"""

from credential_manager import get_credential_manager
credential_manager = get_credential_manager()

import os
import psycopg2
import subprocess
import json
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime, date as _date
from typing import Dict, List, Any
import logging

logger = logging.getLogger(__name__)

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "user": os.getenv("DB_USER", "stocks"),
    "password": credential_manager.get_db_credentials()["password"],
    "database": os.getenv("DB_NAME", "stocks"),
}

# Historical crash periods
CRASH_PERIODS = {
    "2008_financial_crisis": {
        "name": "2008 Financial Crisis",
        "description": "Sep 2008 - Mar 2009: -57% SPY drawdown",
        "start": _date(2008, 9, 1),
        "end": _date(2009, 3, 31),
        "market_dd": -57.0,
    },
    "2020_covid_crash": {
        "name": "2020 COVID Crash",
        "description": "Feb 2020 - Mar 2020: -34% SPY drawdown",
        "start": _date(2020, 2, 1),
        "end": _date(2020, 3, 31),
        "market_dd": -34.0,
    },
    "2022_bear_market": {
        "name": "2022 Bear Market",
        "description": "Jan 2022 - Oct 2022: -26% SPY drawdown",
        "start": _date(2022, 1, 1),
        "end": _date(2022, 10, 31),
        "market_dd": -26.0,
    },
}

# Normal period for comparison
NORMAL_PERIOD = {
    "normal_bull": {
        "name": "Normal Bull Market",
        "description": "2021 Bull Market: +27% SPY return",
        "start": _date(2021, 1, 1),
        "end": _date(2021, 12, 31),
        "market_return": 27.0,
    },
}


class StressTestRunner:
    """Run backtests across historical crash periods."""

    def __init__(self):
        self.results = {}

    def run_backtest(self, period_key: str, period_config: Dict) -> Dict[str, Any]:
        """
        Run backtest for a specific period.

        Returns:
            {
                'period': str,
                'start_date': date,
                'end_date': date,
                'total_trades': int,
                'win_rate': float,
                'sharpe': float,
                'max_dd': float,
                'total_return': float,
                'status': 'success' | 'error',
                'error_msg': str or None,
            }
        """
        print(f"\n{'='*70}")
        print(f"Testing: {period_config['name']}")
        print(f"Period: {period_config['start']} to {period_config['end']}")
        if 'description' in period_config:
            print(f"Context: {period_config['description']}")
        print(f"{'='*70}\n")

        try:
            # Run backtest via subprocess (same as manual run)
            cmd = [
                "python3",
                "algo_backtest.py",
                "--start", str(period_config['start']),
                "--end", str(period_config['end']),
                "--capital", "100000",
                "--max-positions", "12",
            ]

            print(f"Running: {' '.join(cmd)}\n")
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

            if result.returncode != 0:
                return {
                    'period': period_key,
                    'start_date': period_config['start'],
                    'end_date': period_config['end'],
                    'status': 'error',
                    'error_msg': result.stderr,
                    'total_trades': 0,
                    'win_rate': 0,
                    'sharpe': 0,
                    'max_dd': 0,
                    'total_return': 0,
                }

            # Parse results from stdout/stderr
            output = result.stdout + result.stderr

            # Extract metrics (these would be logged by algo_backtest.py)
            metrics = self._parse_backtest_output(output, period_key)

            return {
                'period': period_key,
                'start_date': period_config['start'],
                'end_date': period_config['end'],
                'status': 'success',
                'error_msg': None,
                **metrics,
            }

        except subprocess.TimeoutExpired:
            return {
                'period': period_key,
                'start_date': period_config['start'],
                'end_date': period_config['end'],
                'status': 'error',
                'error_msg': 'Backtest timeout (>5 min)',
                'total_trades': 0,
                'win_rate': 0,
                'sharpe': 0,
                'max_dd': 0,
                'total_return': 0,
            }

        except Exception as e:
            return {
                'period': period_key,
                'start_date': period_config['start'],
                'end_date': period_config['end'],
                'status': 'error',
                'error_msg': str(e),
                'total_trades': 0,
                'win_rate': 0,
                'sharpe': 0,
                'max_dd': 0,
                'total_return': 0,
            }

    def _parse_backtest_output(self, output: str, period_key: str) -> Dict:
        """
        Parse metrics from backtest output.

        This is a placeholder - actual parsing depends on algo_backtest.py output format.
        For now, returns dummy values that should be populated from logs.
        """
        # TODO: Parse actual output from algo_backtest.py
        # For now, placeholder
        return {
            'total_trades': 0,
            'win_rate': 0.0,
            'sharpe': 0.0,
            'max_dd': 0.0,
            'total_return': 0.0,
        }

    def run_all_crashes(self) -> List[Dict]:
        """Run backtests on all crash periods plus one normal period."""
        print("\n" + "="*70)
        print("STRESS TEST SUITE - Historical Market Crashes")
        print("="*70)
        print("\nThis will test system resilience on:")
        print("  1. 2008 Financial Crisis (-57% market)")
        print("  2. 2020 COVID Crash (-34% market)")
        print("  3. 2022 Bear Market (-26% market)")
        print("  4. 2021 Bull Market (+27% market - for comparison)")
        print("\n")

        all_results = []

        # Run crash period tests
        for period_key, period_config in CRASH_PERIODS.items():
            result = self.run_backtest(period_key, period_config)
            all_results.append(result)
            self.results[period_key] = result

        # Run normal period for comparison
        for period_key, period_config in NORMAL_PERIOD.items():
            result = self.run_backtest(period_key, period_config)
            all_results.append(result)
            self.results[period_key] = result

        return all_results

    def print_summary(self):
        """Print summary report."""
        print("\n" + "="*70)
        print("STRESS TEST RESULTS SUMMARY")
        print("="*70 + "\n")

        # Table format
        print(f"{'Period':<25} {'Trades':>8} {'Win%':>7} {'Sharpe':>8} {'Max DD':>8} {'Return%':>8}")
        print("-" * 70)

        for period_key, result in self.results.items():
            period_name = CRASH_PERIODS.get(period_key, NORMAL_PERIOD.get(period_key, {})).get('name', period_key)

            if result['status'] == 'error':
                print(f"{period_name:<25} {'ERROR':<8} {result['error_msg'][:40]}")
            else:
                print(
                    f"{period_name:<25} "
                    f"{result['total_trades']:>8} "
                    f"{result['win_rate']:>6.1f}% "
                    f"{result['sharpe']:>8.2f} "
                    f"{result['max_dd']:>7.1f}% "
                    f"{result['total_return']:>7.1f}%"
                )

        print("\n" + "-" * 70)
        self._print_analysis()

    def _print_analysis(self):
        """Print analysis and red flags."""
        print("\nKEY INSIGHTS:")

        # Check if crash periods have lower Sharpe
        crash_sharpes = [r['sharpe'] for r in self.results.values()
                        if r['period'] in CRASH_PERIODS and r['status'] == 'success']
        normal_sharpes = [r['sharpe'] for r in self.results.values()
                         if r['period'] in NORMAL_PERIOD and r['status'] == 'success']

        if crash_sharpes and normal_sharpes:
            avg_crash = sum(crash_sharpes) / len(crash_sharpes)
            avg_normal = sum(normal_sharpes) / len(normal_sharpes)

            degradation = ((avg_normal - avg_crash) / avg_normal * 100) if avg_normal > 0 else 0
            print(f"  • Sharpe degradation in crashes: {degradation:.1f}%")

            if degradation > 50:
                print(f"    ⚠️  WARNING: System significantly degraded during crashes")
            else:
                print(f"    ✓ System maintained resilience")

        # Check win rates
        crash_wr = [r['win_rate'] for r in self.results.values()
                   if r['period'] in CRASH_PERIODS and r['status'] == 'success']
        if crash_wr:
            avg_wr = sum(crash_wr) / len(crash_wr)
            print(f"  • Average win rate during crashes: {avg_wr:.1f}%")
            if avg_wr < 30:
                print(f"    ⚠️  WARNING: Win rate collapsed (<30%)")

        # Check returns
        crash_returns = [r['total_return'] for r in self.results.values()
                        if r['period'] in CRASH_PERIODS and r['status'] == 'success']
        if crash_returns:
            profitable = sum(1 for r in crash_returns if r > 0)
            print(f"  • Profitable during crashes: {profitable}/{len(crash_returns)} periods")
            if profitable == 0:
                print(f"    ⚠️  WARNING: System lost money in all crash periods")
            else:
                print(f"    ✓ System profitable in {profitable} crash period(s)")

        # Check drawdowns
        crash_dds = [r['max_dd'] for r in self.results.values()
                    if r['period'] in CRASH_PERIODS and r['status'] == 'success']
        if crash_dds:
            max_dd = max(crash_dds)
            print(f"  • Worst drawdown during crashes: {max_dd:.1f}%")
            if max_dd > 40:
                print(f"    ⚠️  WARNING: Drawdown exceeded circuit breaker threshold")

        print("\n" + "="*70)

    def save_results(self, filename: str = 'STRESS_TEST_RESULTS.json'):
        """Save results to JSON file."""
        with open(filename, 'w') as f:
            json.dump(self.results, f, indent=2, default=str)
        print(f"\nResults saved to: {filename}")


if __name__ == '__main__':
    runner = StressTestRunner()
    runner.run_all_crashes()
    runner.print_summary()
    runner.save_results('STRESS_TEST_RESULTS.json')
