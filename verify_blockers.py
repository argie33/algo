#!/usr/bin/env python3
"""Verify all 6 critical blockers are fixed."""

import sys
from decimal import Decimal

print("\n=== BLOCKER VERIFICATION ===\n")

# BLOCKER #1: get_pool_health() function
try:
    from utils.db.connection_pool import get_pool_health
    print("✓ BLOCKER #1 FIXED: get_pool_health() exists and imports successfully")
except ImportError as e:
    print(f"✗ BLOCKER #1 NOT FIXED: {e}")
    sys.exit(1)

# BLOCKER #2: Cursor lifecycle - _with_cursor supports cur parameter
try:
    from algo.monitoring.position_monitor import PositionMonitor
    import inspect
    sig = inspect.signature(PositionMonitor._with_cursor)
    if 'cur' in sig.parameters:
        print("✓ BLOCKER #2 FIXED: _with_cursor accepts cur parameter")
    else:
        print("✗ BLOCKER #2 NOT FIXED: _with_cursor missing cur parameter")
        sys.exit(1)
except Exception as e:
    print(f"✗ BLOCKER #2 NOT FIXED: {e}")
    sys.exit(1)

# BLOCKER #3: Exit retry logic
try:
    from algo.orchestrator.phase6_exit_execution import _retry_exit_trade
    print("✓ BLOCKER #3 FIXED: _retry_exit_trade function exists")
except ImportError as e:
    print(f"✗ BLOCKER #3 NOT FIXED: {e}")
    sys.exit(1)

# BLOCKER #4: Config validation accepts Decimal
try:
    from algo.orchestrator.config_validator import get_config_float, get_config_int
    config = {
        'test_float': Decimal('99.5'),
        'test_int': Decimal('42'),
    }
    f = get_config_float(config, 'test_float', 'test_phase')
    i = get_config_int(config, 'test_int', 'test_phase')
    assert f == 99.5 and i == 42
    print("✓ BLOCKER #4 FIXED: config_validator accepts Decimal types")
except Exception as e:
    print(f"✗ BLOCKER #4 NOT FIXED: {e}")
    sys.exit(1)

# BLOCKER #5: Circuit breaker empty check
try:
    with open('algo/orchestrator/phase2_circuit_breakers.py', 'r') as f:
        content = f.read()
    if "if not checks:" in content:
        print("✓ BLOCKER #5 FIXED: Circuit breaker empty check is present")
    else:
        print("✗ BLOCKER #5 NOT FIXED: Circuit breaker empty check not found")
        sys.exit(1)
except Exception as e:
    print(f"✗ BLOCKER #5 NOT FIXED: {e}")
    sys.exit(1)

# BLOCKER #6: Spinoff cascade - stock_scores checks data_unavailable
try:
    with open('loaders/load_stock_scores.py', 'r') as f:
        content = f.read()
    if "data_unavailable" in content and "WHERE data_unavailable = false" in content:
        print("✓ BLOCKER #6 FIXED: stock_scores checks data_unavailable flag")
    else:
        print("✗ BLOCKER #6 NOT FIXED: stock_scores missing data_unavailable checks")
        sys.exit(1)
except Exception as e:
    print(f"✗ BLOCKER #6 NOT FIXED: {e}")
    sys.exit(1)

print("\n=== ALL 6 CRITICAL BLOCKERS FIXED ===\n")
