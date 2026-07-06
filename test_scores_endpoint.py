#!/usr/bin/env python3
import sys
sys.path.insert(0, './lambda/api')
sys.path.insert(0, './lambda/api/..')
sys.path.insert(0, './lambda/api/../..')

from utils.db.context import DatabaseContext

def matches_route(request_path, route_prefix):
    if request_path == route_prefix:
        return True
    if request_path.startswith(route_prefix + '/'):
        return True
    return False

# Import from the correct path
sys.path.insert(0, './lambda/api')
from api_router import _HANDLER_CONFIG

test_path = '/api/algo/scores'
print(f'Testing path: {test_path}')
print()

for i, (prefix, module_name) in enumerate(_HANDLER_CONFIG):
    if matches_route(test_path, prefix):
        print(f'FIRST MATCH: {prefix} -> {module_name}')
        break
    if i < 5:
        print(f'  No match {i}: {prefix}')

print()
print('Now testing if algo handler handles this path...')
print()

with DatabaseContext('read') as cur:
    from routes import algo
    path = '/api/algo/scores'
    try:
        response = algo.handle(cur, path, 'GET', {})
        status = response.get('statusCode')

        print(f'Response statusCode: {status}')
        print()

        if status == 500:
            print('ERROR DETAILS:')
            for key in ['message', 'errorType', '_error', 'data']:
                val = response.get(key)
                if val:
                    print(f'  {key}: {str(val)[:1000]}')  # Print first 1000 chars
    except Exception as e:
        print(f'EXCEPTION in algo.handle: {type(e).__name__}: {e}')
        import traceback
        traceback.print_exc()
    else:
        data = response.get('data', {})
        top_count = len(data.get('top', []))

        print(f'Response has top field: {bool(data.get("top"))}')
        print(f'Number of items in top: {top_count}')

        if data.get('top'):
            first = data['top'][0]
            print()
            print('First item (sample):')
            print(f'  symbol: {first.get("symbol")}')
            print(f'  growth_score: {first.get("growth_score")}')
            print(f'  composite_score: {first.get("composite_score")}')
