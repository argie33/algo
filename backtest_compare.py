#!/usr/bin/env python3
"""
Strategy Comparison Backtester

Runs the same date range through multiple strategy configurations
and produces a side-by-side comparison table. Use this to:

  1. Measure the raw signal quality (pure buy/sell, no filters)
  2. See how each filter layer adds or removes value
  3. Validate that the full pipeline beats the baseline

Strategies run in sequence:
  raw      - Pure buy/sell signals. No filters whatsoever. BASELINE.
  filtered - 5-tier filter pipeline (data quality, market health, trend,
             signal quality, portfolio fit). No advanced scoring.
  advanced - Full system: 5-tier + advanced filters + swing-score ranking.

Usage:
    python3 backtest_compare.py --start 2024-01-01 --end 2025-12-31
    python3 backtest_compare.py --start 2023-01-01 --end 2025-12-31 --capital 50000
    python3 backtest_compare.py --start 2024-01-01 --end 2025-12-31 --strategies raw filtered
"""

import argparse
import json
import sys
from datetime import date as _date
from pathlib import Path

# Allow running from repo root
sys.path.insert(0, str(Path(__file__).parent / 'lambda-deploy'))

from algo_backtest import Backtester, STRATEGIES


def run_comparison(start, end, capital, max_positions, risk_pct, max_hold,
                   strategies=None):
    if strategies is None:
        strategies = list(STRATEGIES)

    results = {}
    for strat in strategies:
        print(f"\n\n{'#'*70}")
        print(f"# Running strategy: {strat.upper()}")
        print(f"{'#'*70}")
        bt = Backtester(
            start_date=start,
            end_date=end,
            initial_capital=capital,
            max_positions=max_positions,
            base_risk_pct=risk_pct,
            max_hold_days=max_hold,
            strategy=strat,
        )
        results[strat] = bt.run()

    _print_comparison(results, strategies)
    return results


def _print_comparison(results, strategies):
    cols = strategies
    width = 14

    def row(label, key, fmt='{:.2f}', suffix=''):
        vals = []
        for s in cols:
            r = results.get(s, {})
            v = r.get(key)
            if v is None:
                vals.append('N/A'.rjust(width))
            else:
                try:
                    vals.append((fmt.format(v) + suffix).rjust(width))
                except (TypeError, ValueError):
                    vals.append(str(v).rjust(width))
        return f"  {label:<25}" + ''.join(vals)

    header = f"  {'Metric':<25}" + ''.join(s.upper().rjust(width) for s in cols)
    sep = '-' * (25 + width * len(cols) + 2)

    print(f"\n\n{'='*70}")
    print("STRATEGY COMPARISON SUMMARY")
    print(f"  Period  : {results[cols[0]].get('period', 'N/A')}")
    print(f"  Capital : ${results[cols[0]].get('initial_capital', 0):,.0f}")
    print('='*70)
    print(header)
    print(sep)
    print(row('Total Return %',       'total_return_pct',    '{:+.2f}', '%'))
    print(row('CAGR %',               'cagr_pct',             '{:+.2f}', '%'))
    print(row('SPY Buy-Hold %',       'spy_buy_hold_pct',     '{:+.2f}', '%'))
    print(row('Alpha vs SPY %',       'alpha_vs_spy_pct',     '{:+.2f}', '%'))
    print(sep)
    print(row('Closed Trades',        'closed_trades',        '{:.0f}'))
    print(row('Win Rate %',           'win_rate_pct',         '{:.1f}', '%'))
    print(row('Avg R / Trade',        'avg_r_per_trade',      '{:+.2f}', 'R'))
    print(row('Avg Win R',            'avg_win_r',            '{:+.2f}', 'R'))
    print(row('Avg Loss R',           'avg_loss_r',           '{:+.2f}', 'R'))
    print(row('Profit Factor',        'profit_factor',        '{:.2f}'))
    print(row('Expectancy (R)',       'expectancy_r',         '{:+.3f}', 'R'))
    print(sep)
    print(row('Max Drawdown %',       'max_drawdown_pct',     '{:.2f}', '%'))
    print(row('Sharpe Ratio',         'sharpe_ratio',         '{:.2f}'))
    print(row('Sortino Ratio',        'sortino_ratio',        '{:.2f}'))
    print(row('Avg Hold Days',        'avg_hold_days',        '{:.1f}', 'd'))
    print('='*70)

    # Year-by-year per strategy
    for strat in cols:
        by_year = results.get(strat, {}).get('per_year', {})
        if by_year:
            print(f"\n  {strat.upper()} — Year by Year:")
            for yr, ydata in sorted(by_year.items()):
                print(f"    {yr}:  {ydata['trades']:3d} trades | "
                      f"WR {ydata['win_rate']:4.1f}% | "
                      f"Avg R {ydata['avg_r']:+.2f} | "
                      f"P&L ${ydata['pnl_dollars']:+,.0f}")

    print()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Compare backtest strategies side by side')
    parser.add_argument('--start', type=str, default='2024-01-01')
    parser.add_argument('--end', type=str, default='2025-12-31')
    parser.add_argument('--capital', type=float, default=100_000.0)
    parser.add_argument('--max-positions', type=int, default=12)
    parser.add_argument('--risk-pct', type=float, default=0.75,
                        help='Risk per trade as %% of portfolio (default 0.75)')
    parser.add_argument('--max-hold', type=int, default=20,
                        help='Max hold days (default 20)')
    parser.add_argument('--strategies', nargs='+', choices=STRATEGIES, default=list(STRATEGIES),
                        help='Strategies to compare (default: all three)')
    args = parser.parse_args()

    results = run_comparison(
        start=_date.fromisoformat(args.start),
        end=_date.fromisoformat(args.end),
        capital=args.capital,
        max_positions=args.max_positions,
        risk_pct=args.risk_pct,
        max_hold=args.max_hold,
        strategies=args.strategies,
    )

    print(f"\n[Done] To run a single strategy:")
    print(f"  python3 lambda-deploy/algo_backtest.py --strategy raw --start {args.start} --end {args.end}")
    print(f"  python3 lambda-deploy/algo_backtest.py --strategy filtered --start {args.start} --end {args.end}")
    print(f"  python3 lambda-deploy/algo_backtest.py --strategy advanced --start {args.start} --end {args.end}")
