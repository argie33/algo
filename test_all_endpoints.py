#!/usr/bin/env python3
"""Test all dashboard endpoints to verify 5xx errors are fixed."""

import os
import sys
sys.path.insert(0, '.')
sys.path.insert(0, 'api-pkg')
os.environ['SKIP_PANEL_REGISTRY'] = '1'

from utils.db.context import DatabaseContext
from routes.algo_handlers.monitoring import _get_algo_audit_log
from routes.algo_handlers.orchestration import _get_orchestrator_execution_recent
from routes.algo_handlers.dashboard import _get_circuit_breakers, _get_algo_positions, _get_algo_trades, _get_algo_status

def test_endpoint(name: str, handler_func, *args, **kwargs):
    """Test an endpoint handler."""
    print(f'\nTesting: {name}')
    try:
        result = handler_func(*args, **kwargs)
        status = result.get('statusCode', '?')
        print(f'  Status: {status}')
        if status == 200:
            data = result.get('data')
            if isinstance(data, list):
                print(f'  [OK] SUCCESS: {len(data)} items')
            else:
                print(f'  [OK] SUCCESS: data returned')
        elif status == 503:
            msg = result.get('message', '')
            print(f'  [WARN] DEGRADED (503): {msg[:100]}')
        else:
            print(f'  [ERROR] {result.get("message", "unknown")}')
    except Exception as e:
        print(f'  [ERROR] EXCEPTION: {type(e).__name__}: {e}')

print("=" * 60)
print("Testing All Dashboard Endpoints")
print("=" * 60)

with DatabaseContext('write') as cur:
    # Test critical endpoints
    test_endpoint('audit_log', _get_algo_audit_log, cur, limit=5, offset=0)
    test_endpoint('execution_recent', _get_orchestrator_execution_recent, cur)
    test_endpoint('circuit_breakers', _get_circuit_breakers, cur)
    test_endpoint('positions', _get_algo_positions, cur)
    test_endpoint('trades', _get_algo_trades, cur, limit=50)
    test_endpoint('status', _get_algo_status, cur)

print("\n" + "=" * 60)
print("Summary: All endpoints tested")
print("=" * 60)
