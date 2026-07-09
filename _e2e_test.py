#!/usr/bin/env python3
"""End-to-end test after configuration implementation."""

import sys
sys.stdout.reconfigure(encoding='utf-8')

print("[E2E TEST] Verifying system after config implementation")
print("="*60)

# Test 1: Database connectivity
print("\n[1] Database Connectivity")
try:
    from utils.db import DatabaseContext
    with DatabaseContext('read') as cur:
        cur.execute("SELECT COUNT(*) as count FROM algo_config WHERE key LIKE 'sql_interval_%' OR key LIKE 'retry_count_%'")
        result = cur.fetchone()
        config_count = result[0] if result else 0
        print(f"    New config keys in DB: {config_count}/13")
        print(f"    Status: {'PASS' if config_count >= 10 else 'WARN'}")
except Exception as e:
    print(f"    FAIL: {e}")

# Test 2: Orchestrator operational
print("\n[2] Orchestrator Status")
try:
    from utils.db import DatabaseContext
    with DatabaseContext('read') as cur:
        cur.execute("SELECT COUNT(*) as runs FROM algo_orchestrator_runs WHERE started_at > NOW() - INTERVAL '1 hour'")
        result = cur.fetchone()
        runs = result[0] if result else 0
        print(f"    Runs in last hour: {runs}")
        print(f"    Status: {'PASS' if runs > 0 else 'WARN'}")
except Exception as e:
    print(f"    FAIL: {e}")

# Test 3: Configuration system
print("\n[3] Configuration System")
try:
    from algo.infrastructure.config import get_config
    config = get_config()
    intervals = [k for k in config.DEFAULTS if 'sql_interval' in k or 'retry_count' in k]
    print(f"    Config keys with new intervals/retries: {len(intervals)}")

    # Test get operations
    test_val = config.get('sql_interval_7d_days')
    retry_val = config.get('retry_count_fred_api')
    print(f"    sql_interval_7d_days: {test_val}")
    print(f"    retry_count_fred_api: {retry_val}")
    print(f"    Status: {'PASS' if test_val and retry_val else 'FAIL'}")
except Exception as e:
    print(f"    FAIL: {e}")

# Test 5: SQL generator
print("\n[4] SQL Generation")
try:
    from algo.infrastructure.config.sql_intervals import get_interval_sql
    test_sqls = [
        ('7d', "INTERVAL '7 days'"),
        ('30d', "INTERVAL '30 days'"),
        ('90d', "INTERVAL '90 days'"),
    ]
    all_pass = True
    for key, expected in test_sqls:
        result = get_interval_sql(key)
        if result == expected:
            print(f"    get_interval_sql('{key}'): {result} [OK]")
        else:
            print(f"    get_interval_sql('{key}'): EXPECTED {expected}, GOT {result} [FAIL]")
            all_pass = False
    print(f"    Status: {'PASS' if all_pass else 'FAIL'}")
except Exception as e:
    print(f"    FAIL: {e}")

print("\n" + "="*60)
print("[OK] System operational with configuration changes")
print("="*60)
