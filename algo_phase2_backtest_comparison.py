#!/usr/bin/env python3
"""
Phase 2 Backtest Comparison - Validate Stage 2 + RS > 70 + Volume + Trendline filters

Runs two backtests:
1. Phase 1 baseline (no Stage 2, RS, volume filters)
2. Phase 2 (with all filters enabled)

Compares metrics to validate signal quality improvements.
"""

import subprocess
import os
import shutil
import tempfile
from pathlib import Path
from datetime import datetime, date as _date
from typing import Dict, Any
import json

PIPELINE_FILE = "algo_filter_pipeline.py"
BACKTEST_SCRIPT = "algo_backtest.py"

# Dates for testing
START_DATE = "2026-01-01"
END_DATE = "2026-05-08"
CAPITAL = 100000
MAX_POSITIONS = 12


def create_phase1_version(original_file: str, temp_file: str) -> None:
    """Create Phase 1 version by disabling Phase 2 filters."""
    with open(original_file, 'r') as f:
        content = f.read()

    # Disable Stage 2 check (lines 140-142)
    # Find the stage check and comment it out
    content = content.replace(
        '                    if stage_number != 2:',
        '                    if False and stage_number != 2:  # DISABLED FOR PHASE 1'
    )

    # Disable RS > 70 check (lines 143-145)
    content = content.replace(
        '                    if rs_rating is None or rs_rating < 70:',
        '                    if False and (rs_rating is None or rs_rating < 70):  # DISABLED FOR PHASE 1'
    )

    # Disable Volume check (lines 147-151)
    content = content.replace(
        '                    if volume and avg_vol_50d and avg_vol_50d > 0:',
        '                    if False and volume and avg_vol_50d and avg_vol_50d > 0:  # DISABLED FOR PHASE 1'
    )

    with open(temp_file, 'w') as f:
        f.write(content)


def run_backtest(phase: str, start: str, end: str, capital: int, max_pos: int) -> Dict[str, Any]:
    """Run backtest and return metrics."""
    print(f"\n{'='*70}")
    print(f"Running {phase} Backtest")
    print(f"Period: {start} to {end}")
    print(f"Capital: ${capital:,}  Max positions: {max_pos}")
    print(f"{'='*70}\n")

    cmd = [
        "python3",
        BACKTEST_SCRIPT,
        "--start", start,
        "--end", end,
        "--capital", str(capital),
        "--max-positions", str(max_pos),
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        output = result.stdout + result.stderr
        print(output)

        # Parse results from output
        metrics = parse_backtest_output(output, phase)
        metrics['status'] = 'success' if result.returncode == 0 else 'error'
        return metrics

    except subprocess.TimeoutExpired:
        return {
            'status': 'timeout',
            'phase': phase,
            'error': 'Backtest exceeded 10 minute timeout'
        }
    except Exception as e:
        return {
            'status': 'error',
            'phase': phase,
            'error': str(e)
        }


def parse_backtest_output(output: str, phase: str) -> Dict[str, Any]:
    """Parse key metrics from backtest output."""
    metrics = {
        'phase': phase,
        'total_trades': 0,
        'win_rate': 0.0,
        'sharpe': 0.0,
        'max_dd': 0.0,
        'total_return': 0.0,
        'profit_factor': 0.0,
        'avg_trade': 0.0,
    }

    # Look for key metrics in output
    for line in output.split('\n'):
        if 'Total trades:' in line or 'trades:' in line.lower():
            try:
                val = int(''.join(filter(str.isdigit, line.split(':')[1])))
                metrics['total_trades'] = val
            except:
                pass
        elif 'Win rate:' in line or 'win rate' in line.lower():
            try:
                val = float(line.split(':')[1].strip().rstrip('%'))
                metrics['win_rate'] = val
            except:
                pass
        elif 'Sharpe' in line and ':' in line:
            try:
                val = float(line.split(':')[1].strip())
                metrics['sharpe'] = val
            except:
                pass
        elif 'Max drawdown' in line or 'Drawdown' in line:
            try:
                val = float(line.split(':')[1].strip().rstrip('%'))
                metrics['max_dd'] = val
            except:
                pass
        elif 'Total return' in line:
            try:
                val = float(line.split(':')[1].strip().rstrip('%'))
                metrics['total_return'] = val
            except:
                pass
        elif 'Profit factor' in line or 'profit factor' in line.lower():
            try:
                val = float(line.split(':')[1].strip())
                metrics['profit_factor'] = val
            except:
                pass

    return metrics


def compare_results(phase1: Dict, phase2: Dict) -> str:
    """Generate comparison report."""
    report = f"""
PHASE 2 BACKTEST COMPARISON REPORT
{'='*70}

PHASE 1 (Baseline - No Stage 2, RS, Volume filters)
  Total Trades:      {phase1['total_trades']}
  Win Rate:          {phase1['win_rate']:.1f}%
  Sharpe Ratio:      {phase1['sharpe']:.2f}
  Max Drawdown:      {phase1['max_dd']:.1f}%
  Total Return:      {phase1['total_return']:.1f}%
  Profit Factor:     {phase1['profit_factor']:.2f}x

PHASE 2 (With Stage 2, RS > 70, Volume, Trendline filters)
  Total Trades:      {phase2['total_trades']}
  Win Rate:          {phase2['win_rate']:.1f}%
  Sharpe Ratio:      {phase2['sharpe']:.2f}
  Max Drawdown:      {phase2['max_dd']:.1f}%
  Total Return:      {phase2['total_return']:.1f}%
  Profit Factor:     {phase2['profit_factor']:.2f}x

IMPROVEMENTS (Phase 2 vs Phase 1)
{'='*70}
"""

    if phase1['total_trades'] > 0:
        trade_change = ((phase2['total_trades'] - phase1['total_trades']) / phase1['total_trades'] * 100)
        report += f"  Trade count:        {phase2['total_trades']} vs {phase1['total_trades']} ({trade_change:+.0f}%)\n"

    if phase1['win_rate'] > 0:
        wr_change = phase2['win_rate'] - phase1['win_rate']
        report += f"  Win rate:           {phase2['win_rate']:.1f}% vs {phase1['win_rate']:.1f}% ({wr_change:+.1f}pp)\n"

    if phase1['sharpe'] > 0:
        sharpe_change = ((phase2['sharpe'] - phase1['sharpe']) / phase1['sharpe'] * 100)
        report += f"  Sharpe ratio:       {phase2['sharpe']:.2f} vs {phase1['sharpe']:.2f} ({sharpe_change:+.0f}%)\n"

    if phase1['max_dd'] > 0:
        dd_change = phase2['max_dd'] - phase1['max_dd']
        report += f"  Max drawdown:       {phase2['max_dd']:.1f}% vs {phase1['max_dd']:.1f}% ({dd_change:+.1f}pp)\n"

    if phase1['profit_factor'] > 0:
        pf_change = ((phase2['profit_factor'] - phase1['profit_factor']) / phase1['profit_factor'] * 100)
        report += f"  Profit factor:      {phase2['profit_factor']:.2f}x vs {phase1['profit_factor']:.2f}x ({pf_change:+.0f}%)\n"

    report += f"\n{'='*70}\n"
    report += "VALIDATION CRITERIA\n"
    report += f"{'='*70}\n"

    checks = []

    # Check 1: Win rate improvement
    if phase2['win_rate'] >= phase1['win_rate'] + 5:
        checks.append(f"[OK] Win rate improved by {phase2['win_rate'] - phase1['win_rate']:.1f}pp (target: +5pp)")
    else:
        checks.append(f"[!] Win rate improved by {phase2['win_rate'] - phase1['win_rate']:.1f}pp (target: +5pp)")

    # Check 2: Sharpe improvement
    if phase2['sharpe'] >= phase1['sharpe'] + 0.3:
        checks.append(f"[OK] Sharpe improved by {phase2['sharpe'] - phase1['sharpe']:.2f} (target: +0.3)")
    else:
        checks.append(f"[!] Sharpe improved by {phase2['sharpe'] - phase1['sharpe']:.2f} (target: +0.3)")

    # Check 3: Max drawdown reduction
    if phase2['max_dd'] <= phase1['max_dd'] - 3:
        checks.append(f"[OK] Max drawdown reduced by {phase1['max_dd'] - phase2['max_dd']:.1f}pp (target: -3pp)")
    else:
        checks.append(f"[!] Max drawdown reduced by {phase1['max_dd'] - phase2['max_dd']:.1f}pp (target: -3pp)")

    # Check 4: Profit factor improvement
    if phase2['profit_factor'] >= phase1['profit_factor'] + 0.3:
        checks.append(f"[OK] Profit factor improved by {phase2['profit_factor'] - phase1['profit_factor']:.2f}x (target: +0.3x)")
    else:
        checks.append(f"[!] Profit factor improved by {phase2['profit_factor'] - phase1['profit_factor']:.2f}x (target: +0.3x)")

    # Check 5: More selective (fewer trades)
    if phase2['total_trades'] <= phase1['total_trades'] * 0.75:
        pct = (1 - phase2['total_trades'] / phase1['total_trades']) * 100
        checks.append(f"[OK] Trade count reduced by {pct:.0f}% (more selective)")
    else:
        checks.append(f"[!] Trade count reduction < 25%")

    for check in checks:
        report += check + "\n"

    report += f"\n{'='*70}\n"

    # Summary
    passed = sum(1 for c in checks if '[OK]' in c)
    total = len(checks)

    if passed == total:
        report += f"✓ ALL CHECKS PASSED ({passed}/{total}) - Phase 2 ready for deployment\n"
    elif passed >= 3:
        report += f"⚠ PARTIAL PASS ({passed}/{total}) - Some improvements present but not all targets met\n"
    else:
        report += f"✗ VALIDATION FAILED ({passed}/{total}) - Phase 2 needs investigation\n"

    report += f"{'='*70}\n"

    return report


def main():
    """Run the comparison."""
    print("\n" + "="*70)
    print("PHASE 2 VALIDATION - Backtest Comparison")
    print("="*70)
    print("\nThis will:")
    print("  1. Run Phase 1 baseline backtest (no Stage 2, RS, Volume filters)")
    print("  2. Run Phase 2 backtest (with all Phase 2 filters enabled)")
    print("  3. Compare metrics to validate signal quality improvements")
    print(f"\nPeriod: {START_DATE} to {END_DATE}")
    print(f"Capital: ${CAPITAL:,}")
    print(f"Max Positions: {MAX_POSITIONS}")
    print("\n")

    # Check if pipeline file exists
    if not Path(PIPELINE_FILE).exists():
        print(f"ERROR: {PIPELINE_FILE} not found")
        return 1

    # Create temporary Phase 1 version
    print("Creating Phase 1 baseline version...")
    phase1_temp = "algo_filter_pipeline_phase1.py"
    create_phase1_version(PIPELINE_FILE, phase1_temp)

    try:
        # Swap in Phase 1 version
        print("Running Phase 1 backtest...")
        shutil.copy(PIPELINE_FILE, PIPELINE_FILE + ".backup")
        shutil.copy(phase1_temp, PIPELINE_FILE)

        phase1_results = run_backtest(
            "PHASE 1 BASELINE",
            START_DATE, END_DATE, CAPITAL, MAX_POSITIONS
        )

        # Restore Phase 2 version
        print("\nRestoring Phase 2 filters...")
        shutil.copy(PIPELINE_FILE + ".backup", PIPELINE_FILE)

        # Run Phase 2 backtest
        print("Running Phase 2 backtest...")
        phase2_results = run_backtest(
            "PHASE 2",
            START_DATE, END_DATE, CAPITAL, MAX_POSITIONS
        )

        # Generate comparison
        comparison = compare_results(phase1_results, phase2_results)
        print(comparison)

        # Save results
        results = {
            'timestamp': datetime.now().isoformat(),
            'period': f"{START_DATE} to {END_DATE}",
            'phase1': phase1_results,
            'phase2': phase2_results,
        }

        with open('PHASE2_COMPARISON_RESULTS.json', 'w') as f:
            json.dump(results, f, indent=2, default=str)

        with open('PHASE2_COMPARISON_RESULTS.md', 'w') as f:
            f.write(comparison)

        print(f"\nResults saved to PHASE2_COMPARISON_RESULTS.json and PHASE2_COMPARISON_RESULTS.md")

        return 0

    finally:
        # Cleanup
        if Path(phase1_temp).exists():
            os.remove(phase1_temp)
        if Path(PIPELINE_FILE + ".backup").exists():
            os.remove(PIPELINE_FILE + ".backup")


if __name__ == '__main__':
    exit(main())
