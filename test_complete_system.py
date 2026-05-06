#!/usr/bin/env python3
"""
Complete System Validation — Prove all 9 phases work end-to-end

Tests each phase:
  Phase 1: Data freshness & circuit breakers
  Phase 2: Test suite
  Phase 3: Position monitoring
  Phase 4: Performance metrics & pyramid adds
  Phase 5: Pre-trade checks
  Phase 6: Corporate actions & market events
  Phase 7: Walk-forward, stress tests, paper trading gates
  Phase 8: VaR/CVaR risk metrics
  Phase 9: Model governance

Returns: JSON report with all phase validation results
"""

import os
import json
import sys
import subprocess
from pathlib import Path
from datetime import date
from typing import Dict, Any

def run_command(cmd: list, description: str) -> Dict[str, Any]:
    """Execute command and capture result."""
    print(f"\n{'='*80}")
    print(f"{description}")
    print(f"{'='*80}")
    try:
        result = subprocess.run(
            cmd,
            cwd=Path(__file__).parent,
            capture_output=True,
            text=True,
            timeout=120
        )
        success = result.returncode == 0
        print(f"Status: {'[PASS]' if success else '[FAIL]'}")
        if result.stdout:
            print(result.stdout[:500])  # First 500 chars
        if result.stderr and not success:
            print(f"Error: {result.stderr[:500]}")
        return {
            'success': success,
            'stdout_preview': result.stdout[:200] if result.stdout else '',
            'stderr': result.stderr[:200] if result.stderr else '',
            'returncode': result.returncode,
        }
    except subprocess.TimeoutExpired:
        print(f"Status: [TIMEOUT] (>120s)")
        return {'success': False, 'error': 'timeout'}
    except Exception as e:
        print(f"Status: [ERROR] {e}")
        return {'success': False, 'error': str(e)}

def main():
    print(f"\n{'#'*80}")
    print(f"# COMPLETE SYSTEM VALIDATION - All 9 Phases")
    print(f"# {date.today()}")
    print(f"{'#'*80}")

    results = {}

    # Phase 1-7: Orchestrator full pipeline
    print(f"\n\n{'='*80}")
    print(f"PHASES 1-7: Full Orchestrator Pipeline (7-phase daily cycle)")
    print(f"{'='*80}")

    orchestrator_result = run_command(
        ['python3', 'algo_orchestrator.py', '--dry-run'],
        "Orchestrator --dry-run (all 7 phases)"
    )
    results['phases_1_to_7_orchestrator'] = orchestrator_result

    # Phase 2: Test Suite
    print(f"\n\n{'='*80}")
    print(f"PHASE 2: Test Suite (Unit + Integration Tests)")
    print(f"{'='*80}")

    pytest_result = run_command(
        ['pytest', 'tests/', '-v', '--tb=short'],
        "pytest suite (all unit and integration tests)"
    )
    results['phase_2_tests'] = pytest_result

    # Phase 7a: Walk-Forward Optimization
    print(f"\n\n{'='*80}")
    print(f"PHASE 7a: Walk-Forward Optimization (curve-fit detection)")
    print(f"{'='*80}")

    wfo_result = run_command(
        ['python3', 'algo_backtest.py', '--walk-forward', '--start', '2023-01-01', '--end', '2025-12-31'],
        "Walk-Forward Optimization with WFE metric"
    )
    results['phase_7a_walkforward'] = wfo_result

    # Phase 7b: Crisis Stress Testing
    print(f"\n\n{'='*80}")
    print(f"PHASE 7b: Crisis Stress Testing (4 historical crises)")
    print(f"{'='*80}")

    stress_result = run_command(
        ['python3', 'algo_stress_test.py'],
        "Stress test through GFC, COVID, rate shock, dot-com"
    )
    results['phase_7b_stress'] = stress_result

    # Phase 7c: Paper Trading Acceptance Gates
    print(f"\n\n{'='*80}")
    print(f"PHASE 7c: Paper Trading Acceptance Gates (6 formal criteria)")
    print(f"{'='*80}")

    gates_result = run_command(
        ['python3', 'algo_paper_trading_gates.py',
         '--backtest-sharpe', '1.5',
         '--backtest-wr', '55.0',
         '--backtest-dd', '-15.0'],
        "Paper trading validation (6 gates)"
    )
    results['phase_7c_paper_gates'] = gates_result

    # Phase 8: VaR Validation
    print(f"\n\n{'='*80}")
    print(f"PHASE 8: VaR/CVaR Risk Metrics (4 validation tests)")
    print(f"{'='*80}")

    var_result = run_command(
        ['python3', 'validate_var.py'],
        "VaR/CVaR validation (historical, CVaR, stressed, crisis)"
    )
    results['phase_8_var'] = var_result

    # Phase 9: Model Governance
    print(f"\n\n{'='*80}")
    print(f"PHASE 9: Model Governance (registry + IC monitoring)")
    print(f"{'='*80}")

    gov_result = run_command(
        ['python3', 'algo_model_governance.py'],
        "Model governance (registry, IC, champion/challenger)"
    )
    results['phase_9_governance'] = gov_result

    # Summary
    print(f"\n\n{'='*80}")
    print(f"VALIDATION SUMMARY")
    print(f"{'='*80}\n")

    passed = sum(1 for r in results.values() if r.get('success'))
    total = len(results)

    for phase, result in results.items():
        status = "[PASS]" if result.get('success') else "[FAIL]"
        print(f"  {phase:40s} {status}")

    print(f"\n  Result: {passed}/{total} phases validated successfully")

    if passed == total:
        print(f"\n*** [SUCCESS] ALL 9 PHASES VALIDATED — SYSTEM COMPLETE AND OPERATIONAL ***\n")
        return 0
    else:
        print(f"\n*** [ALERT] {total - passed} phase(s) need attention ***\n")
        return 1

if __name__ == '__main__':
    sys.exit(main())
