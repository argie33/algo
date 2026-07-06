#!/usr/bin/env python3
"""Debug individual failing endpoints to identify root causes."""

import sys
import os
sys.path.insert(0, '.')

# Set up database for local dev
os.environ['DB_HOST'] = 'localhost'
os.environ['DB_NAME'] = 'stocks'
os.environ['DB_USER'] = 'stocks'
os.environ['DB_PASSWORD'] = ''

from utils.db import DatabaseContext
from datetime import date
import logging

logging.basicConfig(level=logging.DEBUG)

# Test each failing endpoint with actual handler calls
endpoints_to_test = [
    ("activity", "monitoring", "_get_algo_audit_log", lambda cur: __import__('routes.algo_handlers.monitoring', fromlist=['_get_algo_audit_log'])._get_algo_audit_log(cur, 100, 0, None)),
    ("notifs", "monitoring", "_get_notifications", lambda cur: __import__('routes.algo_handlers.monitoring', fromlist=['_get_notifications'])._get_notifications(cur, {}, None)),
    ("sentiment", "external", "_get_sentiment", lambda cur: __import__('routes.algo_handlers.external', fromlist=['_get_sentiment'])._get_sentiment(cur)),
    ("econ_cal", "external", "_get_economic_calendar", lambda cur: __import__('routes.algo_handlers.external', fromlist=['_get_economic_calendar'])._get_economic_calendar(cur)),
    ("sig_eval", "signals", "_get_rejection_funnel", lambda cur: __import__('routes.algo_handlers.signals', fromlist=['_get_rejection_funnel'])._get_rejection_funnel(cur)),
    ("sec_rot", "sector", "_get_sector_rotation", lambda cur: __import__('routes.algo_handlers.sector', fromlist=['_get_sector_rotation'])._get_sector_rotation(cur, 180)),
    ("srank", "sectors", "_get_sector_ranking", lambda cur: __import__('routes.sectors', fromlist=['_get_sector_ranking'])._get_sector_ranking(cur)),
    ("perf_anl", "metrics", "_get_performance_analytics", lambda cur: __import__('routes.algo_handlers.metrics', fromlist=['_get_performance_analytics'])._get_performance_analytics(cur)),
]

print("=" * 80)
print("DEBUGGING FAILING ENDPOINTS")
print("=" * 80)
print()

with DatabaseContext() as cur:
    for endpoint_name, module, func, handler in endpoints_to_test:
        try:
            print(f"[TESTING] {endpoint_name:12} ({module}.{func}) ... ", end="", flush=True)
            result = handler(cur)
            status = result.get('statusCode', 'unknown')

            if status == 200:
                print(f"OK (200)")
            else:
                print(f"ERROR ({status})")
                if 'message' in result:
                    print(f"  Message: {result['message'][:100]}")
                if '_error' in result:
                    print(f"  Error: {result['_error'][:100]}")
        except Exception as e:
            print(f"EXCEPTION")
            print(f"  {type(e).__name__}: {str(e)[:200]}")
            import traceback
            print(f"  Traceback:")
            for line in traceback.format_exc().split('\n')[-5:-1]:
                if line.strip():
                    print(f"    {line}")

print()
print("=" * 80)
