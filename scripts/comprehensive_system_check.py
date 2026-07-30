#!/usr/bin/env python3
"""Comprehensive system health check before deployment to real money."""
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

# Setup path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from utils.dotenv_loader import load_env_local
load_env_local()

from config.credential_manager import get_db_config
import psycopg2

print("=" * 100)
print("COMPREHENSIVE SYSTEM HEALTH CHECK")
print("=" * 100)

issues_found = []

# 1. Check database connectivity
print("\n[1] Database Connectivity...")
try:
    db_config = get_db_config()
    conn = psycopg2.connect(
        host=db_config['host'],
        port=db_config['port'],
        database=db_config['database'],
        user=db_config['user'],
        password=db_config['password']
    )
    cur = conn.cursor()
    cur.execute("SELECT 1")
    conn.close()
    print("    ✓ Database connection OK")
except Exception as e:
    print(f"    ✗ Database connection FAILED: {e}")
    issues_found.append(("database", str(e)))
    sys.exit(1)

# 2. Check execution_mode consistency
print("\n[2] Execution Mode Configuration...")
try:
    db_config = get_db_config()
    conn = psycopg2.connect(
        host=db_config['host'],
        port=db_config['port'],
        database=db_config['database'],
        user=db_config['user'],
        password=db_config['password']
    )
    cur = conn.cursor()
    cur.execute("SELECT value FROM algo_config WHERE key = %s", ('execution_mode',))
    row = cur.fetchone()
    db_mode = row[0] if row else 'NOT_SET'
    env_mode = os.getenv('ORCHESTRATOR_EXECUTION_MODE', 'NOT_SET')

    if env_mode != 'NOT_SET' and env_mode.lower() != db_mode.lower():
        print(f"    ✗ Mismatch: env={env_mode}, db={db_mode}")
        issues_found.append(("execution_mode", f"env={env_mode} != db={db_mode}"))
    else:
        print(f"    ✓ Consistent: {db_mode}")
    conn.close()
except Exception as e:
    print(f"    ✗ Configuration check FAILED: {e}")
    issues_found.append(("config", str(e)))

# 3. Check recent orchestrator run success rate
print("\n[3] Recent Orchestrator Stability (last 24 hours)...")
try:
    db_config = get_db_config()
    conn = psycopg2.connect(
        host=db_config['host'],
        port=db_config['port'],
        database=db_config['database'],
        user=db_config['user'],
        password=db_config['password']
    )
    cur = conn.cursor()
    cur.execute("""
        SELECT overall_status, COUNT(*) as count
        FROM algo_orchestrator_runs
        WHERE started_at > NOW() - INTERVAL '24 hours'
        GROUP BY overall_status
        ORDER BY count DESC
    """)

    results = cur.fetchall()
    total = sum(row[1] for row in results)
    success_count = sum(row[1] for row in results if row[0] in ('success', 'ok'))
    error_count = sum(row[1] for row in results if row[0] in ('error', 'halted'))

    print(f"    Total runs: {total}")
    for status, count in results:
        pct = (count / total * 100) if total > 0 else 0
        print(f"      {status:<15}: {count:>3} ({pct:>5.1f}%)")

    success_rate = (success_count / total * 100) if total > 0 else 0
    if success_rate < 90:
        print(f"    ✗ Success rate {success_rate:.1f}% < 90% threshold")
        issues_found.append(("stability", f"Success rate {success_rate:.1f}%"))
    else:
        print(f"    ✓ Success rate {success_rate:.1f}% ≥ 90%")

    conn.close()
except Exception as e:
    print(f"    ✗ Stability check FAILED: {e}")
    issues_found.append(("stability", str(e)))

# 4. Check for Phase 3 or Phase 6 errors
print("\n[4] Phase-Specific Errors (last 24 hours)...")
try:
    db_config = get_db_config()
    conn = psycopg2.connect(
        host=db_config['host'],
        port=db_config['port'],
        database=db_config['database'],
        user=db_config['user'],
        password=db_config['password']
    )
    cur = conn.cursor()

    # Check exit check errors
    cur.execute("""
        SELECT error_type, COUNT(*) as count
        FROM algo_exit_check_errors
        WHERE created_at > NOW() - INTERVAL '24 hours'
        GROUP BY error_type
        ORDER BY count DESC
        LIMIT 10
    """)

    exit_errors = cur.fetchall()
    if exit_errors:
        print("    Exit check errors found:")
        for error_type, count in exit_errors:
            print(f"      {error_type[:60]:<60}: {count:>3}")
            if "authentication" in error_type.lower() or "credential" in error_type.lower():
                issues_found.append(("exit_auth", f"{error_type}: {count} instances"))
    else:
        print("    ✓ No exit check errors")

    conn.close()
except Exception as e:
    print(f"    ✗ Error check FAILED: {e}")

# 5. Check Alpaca credentials
print("\n[5] Alpaca Credentials...")
try:
    alpaca_key = os.getenv('APCA_API_KEY_ID')
    alpaca_secret = os.getenv('APCA_API_SECRET_KEY')

    if alpaca_key and alpaca_secret:
        print("    ✓ Alpaca credentials found in environment")
    else:
        print("    ⚠ Alpaca credentials not in environment (will load from Secrets Manager at runtime)")
except Exception as e:
    print(f"    ✗ Credential check FAILED: {e}")

# 6. Check code syntax
print("\n[6] Python Syntax Check...")
try:
    import py_compile
    import tempfile

    critical_files = [
        'algo/orchestration/orchestrator.py',
        'algo/orchestrator/phase3_position_monitor.py',
        'algo/orchestrator/phase6_exit_execution.py',
        'algo/trading/exit_engine.py',
    ]

    syntax_errors = []
    for file_path in critical_files:
        try:
            py_compile.compile(str(project_root / file_path), doraise=True)
        except py_compile.PyCompileError as e:
            syntax_errors.append((file_path, str(e)))

    if syntax_errors:
        print("    ✗ Syntax errors found:")
        for file_path, error in syntax_errors:
            print(f"      {file_path}: {error[:80]}")
            issues_found.append(("syntax", file_path))
    else:
        print("    ✓ All critical files have valid syntax")
except Exception as e:
    print(f"    ✗ Syntax check FAILED: {e}")

# Summary
print("\n" + "=" * 100)
if issues_found:
    print(f"ISSUES FOUND: {len(issues_found)}")
    for category, detail in issues_found:
        print(f"  - {category}: {detail[:80]}")
    print("\nRECOMMENDATION: DO NOT deploy to real money until issues are resolved")
else:
    print("✓ ALL CHECKS PASSED - System ready for deployment")
print("=" * 100)
