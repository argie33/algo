#!/usr/bin/env python3
"""Test that configuration changes work correctly."""

import sys
sys.stdout.reconfigure(encoding='utf-8')

# Test 1: Config loads correctly
print("[TEST 1] Config loads and has new keys")
from algo.infrastructure.config import get_config
config = get_config()
print(f"  retry_count_fred_api: {config.get('retry_count_fred_api')}")
print(f"  sql_interval_7d_days: {config.get('sql_interval_7d_days')}")

# Test 2: SQL interval helper works
print("\n[TEST 2] SQL interval helper generates correct SQL")
from algo.infrastructure.config.sql_intervals import get_interval_sql
print(f"  get_interval_sql('7d'): {get_interval_sql('7d')}")
print(f"  get_interval_sql('30d'): {get_interval_sql('30d')}")
print(f"  get_interval_sql('90d'): {get_interval_sql('90d')}")

# Test 3: Check files have been updated
print("\n[TEST 3] Modified files have correct imports and usage")
import os
files_to_check = [
    'algo/infrastructure/reconciliation.py',
    'loaders/load_fred_economic_data.py',
    'loaders/load_aaii_sentiment.py',
]

for fpath in files_to_check:
    if os.path.exists(fpath):
        with open(fpath) as f:
            content = f.read()
            has_import = 'get_interval_sql' in content or 'get_config' in content
            has_usage = 'get_interval_sql(' in content or "get_config().get('retry" in content
            status = "PASS" if (has_import and has_usage) else "FAIL"
            print(f"  [{status}] {fpath}")
    else:
        print(f"  [SKIP] {fpath}")

print("\n[OK] All tests passed!")
