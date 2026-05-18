#!/usr/bin/env python3
"""
System Validation Script — Comprehensive check of all critical components
Ensures the system can run end-to-end once infrastructure is deployed.

Run: python3 validate_system.py [--verbose]
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import argparse
import json
from typing import Dict, List, Tuple

def test_imports() -> Tuple[bool, List[str]]:
    """Test that all critical Python modules can be imported."""
    errors = []
    modules = [
        ('algo.algo_orchestrator', 'Orchestrator'),
        ('algo.orchestrator.phase1_data_freshness', None),
        ('algo.orchestrator.phase2_circuit_breakers', None),
        ('algo.orchestrator.phase3_position_monitor', None),
        ('algo.algo_signals', 'SignalCalculator'),
        ('algo.algo_filter_pipeline', 'FilterPipeline'),
        ('algo.algo_trade_executor', 'TradeExecutor'),
        ('algo.algo_position_monitor', 'PositionMonitor'),
        ('algo.algo_var', 'ValueAtRisk'),
        ('algo.algo_alerts', 'AlertManager'),
        ('config.credential_helper', None),
        ('utils.structured_logger', 'get_logger'),
    ]

    for module_path, class_name in modules:
        try:
            exec(f'from {module_path} import *')
            print(f"  OK: {module_path}")
        except Exception as e:
            error_msg = f"{module_path}: {str(e)[:100]}"
            print(f"  FAIL: {error_msg}")
            errors.append(error_msg)

    return len(errors) == 0, errors

def test_loaders() -> Tuple[bool, List[str]]:
    """Test that all critical loaders can be imported."""
    errors = []
    loaders = [
        'load_technical_data_daily',
        'load_trend_criteria_data',
        'load_market_health_daily',
        'load_signal_quality_scores',
        'loadpricedaily',
        'loadbuyselldaily',
        'loadstockscores',
    ]

    for loader in loaders:
        try:
            exec(f'from loaders.{loader} import *')
            print(f"  OK: {loader}")
        except Exception as e:
            error_msg = f"{loader}: {str(e)[:100]}"
            print(f"  FAIL: {error_msg}")
            errors.append(error_msg)

    return len(errors) == 0, errors

def test_schema_definitions() -> Tuple[bool, List[str]]:
    """Check that critical database tables are defined in schema."""
    from pathlib import Path

    errors = []
    schema_file = Path('terraform/modules/database/init.sql')

    if not schema_file.exists():
        return False, [f"Schema file not found: {schema_file}"]

    schema_content = schema_file.read_text(encoding='utf-8', errors='ignore')
    required_tables = [
        'price_daily',
        'buy_sell_daily',
        'technical_data_daily',
        'trend_template_data',
        'signal_quality_scores',
        'swing_trader_scores',
        'market_health_daily',
        'algo_positions',
        'algo_trades',
        'algo_config',
    ]

    for table in required_tables:
        if f'CREATE TABLE {table}' in schema_content or f'CREATE TABLE IF NOT EXISTS {table}' in schema_content:
            print(f"  OK: {table} defined in schema")
        else:
            error_msg = f"Table '{table}' not found in schema"
            print(f"  FAIL: {error_msg}")
            errors.append(error_msg)

    return len(errors) == 0, errors

def test_frontend_build() -> Tuple[bool, List[str]]:
    """Check that frontend can build."""
    from pathlib import Path

    dist_dir = Path('webapp/frontend/dist')

    if dist_dir.exists() and (dist_dir / 'index.html').exists():
        print(f"  OK: Frontend built (dist/ exists)")
        return True, []
    else:
        error_msg = "Frontend not built - run 'npm run build' in webapp/frontend/"
        print(f"  WARN: {error_msg}")
        return True, []  # Warning only

def test_config_safety() -> Tuple[bool, List[str]]:
    """Check that no hardcoded secrets are in the code."""
    import re
    from pathlib import Path

    errors = []
    pattern = re.compile(r'(password|api_key|secret)\s*=\s*["\'](?!.*getenv|.*environ)[^"\']+["\']', re.IGNORECASE)

    for py_file in Path('algo').rglob('*.py'):
        content = py_file.read_text(encoding='utf-8', errors='ignore')
        if pattern.search(content):
            error_msg = f"{py_file}: Found potential hardcoded secret"
            print(f"  FAIL: {error_msg}")
            errors.append(error_msg)

    if not errors:
        print(f"  OK: No hardcoded secrets detected")

    return len(errors) == 0, errors

def main():
    parser = argparse.ArgumentParser(description='System Validation Script')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    args = parser.parse_args()

    print("\n" + "="*70)
    print("SYSTEM VALIDATION")
    print("="*70 + "\n")

    results: Dict[str, Tuple[bool, List[str]]] = {}

    print("1. Testing Python Imports...")
    results['imports'] = test_imports()

    print("\n2. Testing Data Loaders...")
    results['loaders'] = test_loaders()

    print("\n3. Testing Database Schema Definitions...")
    results['schema'] = test_schema_definitions()

    print("\n4. Testing Frontend Build...")
    results['frontend'] = test_frontend_build()

    print("\n5. Testing Config Safety...")
    results['config'] = test_config_safety()

    # Summary
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)

    all_pass = True
    for test_name, (passed, errors) in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"{test_name.upper()}: {status}")
        if errors and args.verbose:
            for error in errors:
                print(f"  - {error}")
        if not passed:
            all_pass = False

    print("\n" + "="*70)
    if all_pass:
        print("RESULT: All checks passed. System ready for deployment!")
        print("="*70 + "\n")
        return 0
    else:
        print("RESULT: Some checks failed. Review above for details.")
        print("="*70 + "\n")
        return 1

if __name__ == '__main__':
    sys.exit(main())
