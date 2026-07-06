#!/usr/bin/env python3
"""Test each failing endpoint to identify root causes."""

import sys
import os

# Get the directory where this script is
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

# Also add api-pkg to path if needed
api_pkg_dir = os.path.join(script_dir, 'api-pkg')
if os.path.exists(api_pkg_dir) and api_pkg_dir not in sys.path:
    sys.path.insert(0, api_pkg_dir)

# Set up database for local dev
os.environ['DB_HOST'] = 'localhost'
os.environ['DB_NAME'] = 'stocks'
os.environ['DB_USER'] = 'stocks'
os.environ['DB_PASSWORD'] = ''

from utils.db import DatabaseContext

# Import failing endpoint handlers
try:
    from routes.algo_handlers.monitoring import (
    _get_algo_audit_log,
    _get_notifications,
)
from routes.algo_handlers.metrics import _get_algo_metrics
from routes.algo_handlers.dashboard import _get_circuit_breakers
from routes.algo_handlers.external import (
    _get_economic_calendar,
    _get_sentiment,
)
from routes.algo_handlers.sector import _get_sector_rotation
from routes.algo_handlers.signals import _get_rejection_funnel
from routes.algo_handlers.orchestration import _get_orchestrator_execution_recent
from routes.sectors import _get_sector_ranking
from routes.industries import _get_industry_ranking

FAILING_ENDPOINTS = {
    "activity": lambda cur: _get_algo_audit_log(cur, limit=100, offset=0, action_type=None),
    "algo_metrics": lambda cur: _get_algo_metrics(cur),
    "audit": lambda cur: _get_algo_audit_log(cur, limit=100, offset=0, action_type=None),
    "cb": lambda cur: _get_circuit_breakers(cur),
    "econ_cal": lambda cur: _get_economic_calendar(cur),
    "exec_hist": lambda cur: _get_orchestrator_execution_recent(cur, days=7, limit=50),
    "notifs": lambda cur: _get_notifications(cur, {}, None),
    "sec_rot": lambda cur: _get_sector_rotation(cur, days=180),
    "sentiment": lambda cur: _get_sentiment(cur),
    "sig_eval": lambda cur: _get_rejection_funnel(cur),
    "srank": lambda cur: _get_sector_ranking(cur),
    "irank": lambda cur: _get_industry_ranking(cur),
}

print("=" * 80)
print("TESTING FAILING ENDPOINTS")
print("=" * 80)
print()

with DatabaseContext() as cur:
    for endpoint_name, handler_func in FAILING_ENDPOINTS.items():
        try:
            print(f"[TESTING] {endpoint_name:12} ... ", end="", flush=True)
            result = handler_func(cur)
            status = result.get('statusCode', 'unknown')
            if status == 200:
                print(f"OK (200)")
            else:
                print(f"FAIL ({status})")
                print(f"  Error: {result.get('message', result)}")
        except Exception as e:
            print(f"ERROR")
            print(f"  {type(e).__name__}: {str(e)[:100]}")

print()
print("=" * 80)
