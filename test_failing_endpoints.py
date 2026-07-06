#!/usr/bin/env python3
"""Test failing endpoints to diagnose issues."""

import sys
sys.path.insert(0, '.')

from dashboard.fetchers_external import (
    fetch_activity, fetch_audit_log, fetch_exec_history, fetch_sentiment
)
from dashboard.fetchers_market import fetch_sector_rotation, fetch_sector_ranking
from dashboard.fetchers_config import fetch_circuit
from dashboard.fetchers_signals import fetch_signal_eval

fetchers = [
    ('activity', fetch_activity),
    ('audit', fetch_audit_log),
    ('exec_hist', fetch_exec_history),
    ('sentiment', fetch_sentiment),
    ('sec_rot', fetch_sector_rotation),
    ('srank', fetch_sector_ranking),
    ('cb', fetch_circuit),
    ('sig_eval', fetch_signal_eval),
]

for name, fetcher in fetchers:
    try:
        print(f'\n{"="*60}')
        print(f'Testing: {name}')
        print("="*60)
        result = fetcher(None)
        if isinstance(result, dict):
            if '_error' in result:
                err = result['_error']
                print(f'ERROR: {err}')
            else:
                print('SUCCESS: Got valid data')
                for k, v in list(result.items())[:3]:
                    print(f'  {k}: {str(v)[:80]}')
        else:
            print(f'Got response type: {type(result).__name__}')
    except Exception as e:
        print(f'EXCEPTION: {type(e).__name__}: {e}')
        import traceback
        traceback.print_exc()

print(f'\n{"="*60}')
print('Done')
print("="*60)
