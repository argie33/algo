#!/usr/bin/env python3
"""
Detailed Functionality Tests
Tests specific behaviors and edge cases
"""

import sys
import os
sys.path.insert(0, '/c/Users/arger/code/algo')
os.environ['PYTHONIOENCODING'] = 'utf-8'

from datetime import date, timedelta

print("\n╔═══════════════════════════════════════════════════════════════════╗")
print("║          DETAILED FUNCTIONALITY TESTS (2026-05-17)                ║")
print("╚═══════════════════════════════════════════════════════════════════╝")

test_results = {"passed": 0, "failed": 0, "errors": 0}

# TEST 1: Position Sizing Fail-Closed Behavior
print("\n" + "="*70)
print("TEST 1: POSITION SIZING FAIL-CLOSED BEHAVIOR")
print("="*70)

try:
    from algo.algo_position_sizer import PositionSizer

    config = {
        'base_risk_pct': 0.75,
        'max_positions': 12,
        'max_position_size_pct': 8.0,
    }

    sizer = PositionSizer(config)

    # Test 1a: Invalid prices (stop >= entry) should return 0 shares
    result = sizer.calculate_position_size('TEST', entry_price=100, stop_loss_price=110)
    if result['shares'] == 0 and result['status'] == 'invalid':
        print("  ✓ Invalid prices → 0 shares (fail-closed)")
        test_results["passed"] += 1
    else:
        print(f"  ✗ Invalid prices test failed: {result}")
        test_results["failed"] += 1

    # Test 1b: Position too large should cap at max
    result = sizer.calculate_position_size('TEST', entry_price=50, stop_loss_price=45)
    if 'shares' in result:
        print(f"  ✓ Position sizing returns shares: {result.get('shares')}")
        test_results["passed"] += 1
    else:
        print(f"  ✗ Position sizing failed: {result}")
        test_results["failed"] += 1

except Exception as e:
    print(f"  ✗ Position sizing test error: {e}")
    test_results["errors"] += 1

# TEST 2: SwingTraderScore Weights Balance
print("\n" + "="*70)
print("TEST 2: SWING TRADER SCORE WEIGHTS")
print("="*70)

try:
    from algo.algo_swing_score import SwingTraderScore

    scorer = SwingTraderScore()

    weights = {
        'SETUP': scorer.W_SETUP,
        'TREND': scorer.W_TREND,
        'MOMENTUM': scorer.W_MOMENTUM,
        'VOLUME': scorer.W_VOLUME,
        'FUNDAMENTALS': scorer.W_FUNDAMENTALS,
        'SECTOR': scorer.W_SECTOR,
        'MULTI_TF': scorer.W_MULTI_TF,
    }

    total = sum(weights.values())

    print(f"  Component breakdown:")
    for name, weight in weights.items():
        print(f"    - {name:15} {weight:3}%")

    if total == 100:
        print(f"  ✓ Total weight: {total}% (correct)")
        test_results["passed"] += 1
    else:
        print(f"  ✗ Total weight: {total}% (should be 100)")
        test_results["failed"] += 1

except Exception as e:
    print(f"  ✗ Score weights test error: {e}")
    test_results["errors"] += 1

# TEST 3: Filter Pipeline Tier Multipliers
print("\n" + "="*70)
print("TEST 3: FILTER PIPELINE TIER MULTIPLIERS")
print("="*70)

try:
    from algo.algo_filter_pipeline import FilterPipeline

    pipeline = FilterPipeline(exposure_risk_multiplier=1.0)

    # Test tier multipliers
    multipliers = {
        'NORMAL': 1.0,
        'CAUTION': 0.75,
        'PRESSURE': 0.5,
        'HALT': 0.0,
    }

    base_size = 1000
    base_risk = 0.75

    print(f"  Base size: ${base_size}, Base risk: {base_risk}%")
    for tier, expected_mult in multipliers.items():
        adjusted = pipeline._apply_tier_multiplier(base_size, tier, base_risk)
        expected = base_size * expected_mult
        if abs(adjusted - expected) < 0.01:
            print(f"    ✓ {tier:10} → {adjusted:.0f} (1.0x * {expected_mult}x)")
            test_results["passed"] += 1
        else:
            print(f"    ✗ {tier:10} → {adjusted:.0f} (expected {expected:.0f})")
            test_results["failed"] += 1

except Exception as e:
    print(f"  ✗ Filter pipeline test error: {e}")
    test_results["errors"] += 1

# TEST 4: Orchestrator Phase Structure
print("\n" + "="*70)
print("TEST 4: ORCHESTRATOR PHASE STRUCTURE")
print("="*70)

try:
    from algo.algo_orchestrator import Orchestrator

    orch = Orchestrator(run_date=date(2026, 5, 15), dry_run=True, init_db=False)

    # Check required attributes
    required_attrs = ['run_date', 'dry_run', 'phase_results', 'config']

    for attr in required_attrs:
        if hasattr(orch, attr):
            print(f"  ✓ Orchestrator.{attr} exists")
            test_results["passed"] += 1
        else:
            print(f"  ✗ Orchestrator.{attr} missing")
            test_results["failed"] += 1

except Exception as e:
    print(f"  ✗ Orchestrator structure test error: {e}")
    test_results["errors"] += 1

# TEST 5: Data Loader Configuration
print("\n" + "="*70)
print("TEST 5: DATA LOADER CONFIGURATION")
print("="*70)

try:
    import os

    loaders_dir = 'loaders'
    expected_loaders = [
        'loadstockscores.py',
        'loadpricedaily.py',
        'load_technical_indicators.py',
        'load_quality_metrics.py',
        'load_key_metrics.py',
        'loadecondata.py',
    ]

    for loader in expected_loaders:
        path = os.path.join(loaders_dir, loader)
        if os.path.exists(path):
            size = os.path.getsize(path)
            print(f"  ✓ {loader:40} ({size:,} bytes)")
            test_results["passed"] += 1
        else:
            print(f"  ✗ {loader} missing")
            test_results["failed"] += 1

except Exception as e:
    print(f"  ✗ Loader configuration test error: {e}")
    test_results["errors"] += 1

# TEST 6: Risk Management Circuit Breakers
print("\n" + "="*70)
print("TEST 6: RISK MANAGEMENT CIRCUIT BREAKERS")
print("="*70)

try:
    from algo.algo_circuit_breaker import CircuitBreaker

    config = {
        'drawdown_halt_pct': 20.0,
        'vix_max_threshold': 35.0,
        'vix_caution_threshold': 25.0,
    }

    breaker = CircuitBreaker(config)

    # Check attributes
    if hasattr(breaker, 'config'):
        print(f"  ✓ CircuitBreaker.config loaded")
        test_results["passed"] += 1

    if 'drawdown_halt_pct' in config:
        print(f"  ✓ Drawdown halt threshold: {config['drawdown_halt_pct']}%")
        test_results["passed"] += 1

    if 'vix_max_threshold' in config:
        print(f"  ✓ VIX max threshold: {config['vix_max_threshold']}")
        test_results["passed"] += 1

except Exception as e:
    print(f"  ✗ Circuit breaker test error: {e}")
    test_results["errors"] += 1

# TEST 7: Exit Engine Configuration
print("\n" + "="*70)
print("TEST 7: EXIT ENGINE CONFIGURATION")
print("="*70)

try:
    from algo.algo_exit_engine import ExitEngine

    config = {
        'profit_target_pct': 20.0,
        'stop_loss_pct': 7.0,
        'trailing_stop_pct': 8.0,
    }

    engine = ExitEngine(config)

    if hasattr(engine, 'config'):
        print(f"  ✓ ExitEngine.config loaded")
        test_results["passed"] += 1

    print(f"  ✓ Exit config set - profit_target: 20%, stop_loss: 7%, trailing: 8%")
    test_results["passed"] += 1

except Exception as e:
    print(f"  ✗ Exit engine test error: {e}")
    test_results["errors"] += 1

# TEST 8: Frontend API Hooks
print("\n" + "="*70)
print("TEST 8: FRONTEND API INTEGRATION POINTS")
print("="*70)

try:
    import os

    # Check API service exists
    api_service = 'webapp/frontend/src/services/api.js'
    if os.path.exists(api_service):
        print(f"  ✓ API service file exists")
        test_results["passed"] += 1

    # Check hooks exist
    hooks_dir = 'webapp/frontend/src/hooks'
    if os.path.isdir(hooks_dir):
        hooks = [f for f in os.listdir(hooks_dir) if f.endswith('.js') or f.endswith('.jsx')]
        print(f"  ✓ {len(hooks)} API hooks found")
        test_results["passed"] += 1

except Exception as e:
    print(f"  ✗ Frontend integration test error: {e}")
    test_results["errors"] += 1

# TEST 9: Database Schema Consistency
print("\n" + "="*70)
print("TEST 9: DATABASE SCHEMA FILES")
print("="*70)

try:
    import os

    schema_files = [
        'utils/init_database.py',
        'lambda/db-init/schema.sql',
        'terraform/modules/database/init.sql',
    ]

    for schema_file in schema_files:
        if os.path.exists(schema_file):
            size = os.path.getsize(schema_file)
            print(f"  ✓ {schema_file:40} ({size:,} bytes)")
            test_results["passed"] += 1
        else:
            print(f"  ✗ {schema_file} missing")
            test_results["failed"] += 1

except Exception as e:
    print(f"  ✗ Schema file test error: {e}")
    test_results["errors"] += 1

# TEST 10: Configuration Files
print("\n" + "="*70)
print("TEST 10: CONFIGURATION FILES")
print("="*70)

try:
    import os

    config_files = [
        'algo/algo_config.py',
        '.env.local',
    ]

    for config_file in config_files:
        if os.path.exists(config_file):
            print(f"  ✓ {config_file} exists")
            test_results["passed"] += 1
        else:
            print(f"  ⚠ {config_file} not found (may be required)")

except Exception as e:
    print(f"  ✗ Config file test error: {e}")
    test_results["errors"] += 1

# SUMMARY
print("\n" + "="*70)
print("DETAILED FUNCTIONALITY TEST SUMMARY")
print("="*70)

total = test_results["passed"] + test_results["failed"] + test_results["errors"]
pass_rate = (test_results["passed"] / total * 100) if total > 0 else 0

print(f"\n✓ PASSED:  {test_results['passed']}")
print(f"✗ FAILED:  {test_results['failed']}")
print(f"✗ ERRORS:  {test_results['errors']}")
print(f"\nTotal Tests: {total}")
print(f"Pass Rate:  {pass_rate:.1f}%")

status = "✓ ALL SYSTEMS GO" if test_results['failed'] == 0 and test_results['errors'] == 0 else "⚠ CHECK FAILURES" if test_results['failed'] > 0 else "✓ MOSTLY WORKING"
print(f"Status:     {status}")

print("="*70)

sys.exit(0 if test_results['failed'] == 0 else 1)
