#!/usr/bin/env python3
"""Diagnose 5xx errors in dashboard endpoints."""

import os
import sys
import json
import traceback

sys.path.insert(0, '.')
os.environ['SKIP_PANEL_REGISTRY'] = '1'

from utils.db.context import DatabaseContext

# Test endpoints by calling handlers directly
endpoints_to_test = [
    ('activity', 'dashboard.api_data_layer', '/api/algo/audit-log'),
    ('audit', 'dashboard.api_data_layer', '/api/algo/audit-log'),
    ('exec_hist', 'dashboard.api_data_layer', '/api/algo/execution/recent'),
    ('sentiment', 'dashboard.api_data_layer', '/api/algo/sentiment'),
    ('sec_rot', 'dashboard.api_data_layer', '/api/algo/sector-rotation'),
    ('srank', 'dashboard.api_data_layer', '/api/sectors'),
    ('cb', 'dashboard.api_data_layer', '/api/algo/circuit-breakers'),
    ('sig_eval', 'dashboard.api_data_layer', '/api/algo/evaluation'),
]

def test_handler(handler_name: str, module_name: str, endpoint_path: str):
    """Test a handler by calling it directly."""
    print(f'\n{"="*60}')
    print(f'Testing: {handler_name} ({endpoint_path})')
    print("="*60)

    try:
        # Import the handler module
        parts = module_name.split('.')
        module = __import__(module_name, fromlist=[parts[-1]])

        # Get the api_call function
        api_call = getattr(module, 'api_call', None)
        if not api_call:
            print(f'ERROR: api_call not found in {module_name}')
            return

        # Call the endpoint
        result = api_call(endpoint_path)

        # Check for errors
        if isinstance(result, dict):
            if '_error' in result:
                print(f'API Error: {result["_error"]}')
            else:
                print(f'Success: Got {list(result.keys())}')
                # Show first few items
                for k, v in list(result.items())[:3]:
                    v_str = str(v)[:100] if not isinstance(v, (dict, list)) else f'{type(v).__name__}({len(v)})'
                    print(f'  {k}: {v_str}')
        else:
            print(f'Unexpected response type: {type(result).__name__}')

    except Exception as e:
        print(f'EXCEPTION: {type(e).__name__}: {e}')
        traceback.print_exc()

print("Diagnosing 5xx errors in dashboard endpoints")
print("=" * 60)

# Test API layer directly
print("\n1. Testing API Layer (api_call function)")
try:
    import dashboard.api_data_layer as adl
    result = adl.api_call('/api/algo/audit-log')
    if '_error' in result:
        print(f'  API Error: {result["_error"]}')
    else:
        print(f'  API Call Success: {len(result)} items in response')
except Exception as e:
    print(f'  API Layer Error: {type(e).__name__}: {e}')

# Test handlers directly
print("\n2. Testing Handlers (database queries)")
handler_tests = [
    ('audit_log', 'api-pkg/routes/algo_handlers/monitoring.py', '_get_algo_audit_log'),
    ('execution_recent', 'api-pkg/routes/algo_handlers/orchestration.py', '_get_orchestrator_execution_recent'),
    ('circuit_breakers', 'api-pkg/routes/algo_handlers/dashboard.py', '_get_circuit_breakers'),
]

for test_name, file_path, func_name in handler_tests:
    try:
        print(f'\n  {test_name}:')
        sys.path.insert(0, 'api-pkg')

        # Import and test
        if 'monitoring' in file_path:
            from routes.algo_handlers.monitoring import _get_algo_audit_log
            with DatabaseContext('write') as cur:
                result = _get_algo_audit_log(cur, limit=5)
                print(f'    Status: {result.get("statusCode")}')
                print(f'    Data items: {len(result.get("data", []))}')
        elif 'orchestration' in file_path:
            from routes.algo_handlers.orchestration import _get_orchestrator_execution_recent
            with DatabaseContext('write') as cur:
                result = _get_orchestrator_execution_recent(cur)
                print(f'    Status: {result.get("statusCode")}')
                data = result.get('data', [])
                print(f'    Data items: {len(data) if isinstance(data, list) else "not a list"}')
        elif 'dashboard' in file_path:
            from routes.algo_handlers.dashboard import _get_circuit_breakers
            with DatabaseContext('write') as cur:
                result = _get_circuit_breakers(cur)
                print(f'    Status: {result.get("statusCode")}')

    except Exception as e:
        print(f'    ERROR: {type(e).__name__}: {e}')

print(f'\n{"="*60}')
print('Diagnosis complete')
