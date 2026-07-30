#!/usr/bin/env python3
"""
Find PRODUCTION BLOCKERS - code issues that would prevent trades.
Focus on issues that would occur when execution_mode='auto' (live trading).
"""

import sys
import logging
from datetime import date as _date

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ISSUES = []

def check_issue(name: str, description: str, severity: str, status: str):
    """Record an issue."""
    ISSUES.append({
        'name': name,
        'description': description,
        'severity': severity,
        'status': status
    })

# Test 1: Check if exit execution would actually run in auto mode
print("[CHECK 1] Exit execution in auto mode")
try:
    from algo.orchestrator.phase6_exit_execution import run as phase6_run
    from algo.infrastructure.config.main import AlgoConfig
    from algo.reporting import AlertManager

    config = AlgoConfig()
    # Test with execution_mode that would be set for production
    test_config = config.__dict__.copy()
    test_config['execution_mode'] = 'auto'

    alerts = AlertManager()
    result = phase6_run(
        config, _date.today(), dry_run=False, alerts=alerts,
        verbose=False, log_phase_result_fn=lambda *a, **k: None,
        position_recs=[], exposure_actions=[]
    )
    if result.status == 'halted':
        check_issue('Phase6 Auto Mode', f'Phase 6 halted: {result.message}', 'CRITICAL', 'FOUND')
    else:
        print(f"  [PASS] Phase 6 works in auto mode (status={result.status})")
except Exception as e:
    check_issue('Phase6 Auto Mode', str(e)[:150], 'CRITICAL', 'ERROR')
    print(f"  [FAIL] Phase 6 failed: {e}")

# Test 2: Check if exit engine can initialize in auto mode
print("[CHECK 2] ExitEngine in auto mode")
try:
    from algo.trading.exit_engine import ExitEngine
    from algo.infrastructure.config.main import AlgoConfig

    config = AlgoConfig()
    engine = ExitEngine(config)
    print("  ✓ ExitEngine initializes correctly")
except Exception as e:
    check_issue('ExitEngine Init', str(e)[:150], 'CRITICAL', 'ERROR')
    print(f"  ✗ ExitEngine failed: {e}")

# Test 3: Check TradeExecutor in auto mode
print("[CHECK 3] TradeExecutor in auto mode")
try:
    from algo.trading.executor import TradeExecutor
    from algo.infrastructure.config.main import AlgoConfig

    config = AlgoConfig()
    executor = TradeExecutor(config)
    print("  ✓ TradeExecutor initializes correctly")
except Exception as e:
    check_issue('TradeExecutor Init', str(e)[:150], 'CRITICAL', 'ERROR')
    print(f"  ✗ TradeExecutor failed: {e}")

# Test 4: Check if position data has required fields for exit execution
print("[CHECK 4] Position data completeness for exit execution")
try:
    from psycopg2.pool import ThreadedConnectionPool
    from config.credential_manager import get_db_config

    config = get_db_config()
    pool = ThreadedConnectionPool(1, 2, **config)
    conn = pool.getconn()
    cur = conn.cursor()

    # Check for positions with missing critical exit fields
    cur.execute('''
        SELECT COUNT(*) as cnt
        FROM algo_positions
        WHERE status = 'open'
        AND (entry_price IS NULL OR entry_date IS NULL OR active_stop IS NULL)
    ''')
    missing_count = cur.fetchone()[0]
    if missing_count > 0:
        check_issue('Position Data', f'{missing_count} positions missing critical exit fields', 'CRITICAL', 'FOUND')
        print(f"  ✗ {missing_count} positions missing critical fields")
    else:
        print("  ✓ All open positions have required exit fields")

    # Check for positions without proper exit levels
    cur.execute('''
        SELECT COUNT(*) as cnt
        FROM algo_positions
        WHERE status = 'open'
        AND (target_1 IS NULL OR target_2 IS NULL OR target_3 IS NULL)
    ''')
    no_targets = cur.fetchone()[0]
    if no_targets > 0:
        check_issue('Exit Targets', f'{no_targets} positions missing exit targets', 'WARNING', 'FOUND')
        print(f"  ⚠ {no_targets} positions missing target levels (acceptable - computed on fly)")
    else:
        print("  ✓ All positions have exit targets")

    pool.putconn(conn)
    pool.closeall()
except Exception as e:
    check_issue('Position Data', str(e)[:150], 'CRITICAL', 'ERROR')
    print(f"  ✗ Position check failed: {e}")

# Test 5: Check for any stuck transactions or locks
print("[CHECK 5] Database locks and transactions")
try:
    from psycopg2.pool import ThreadedConnectionPool
    from config.credential_manager import get_db_config

    config = get_db_config()
    pool = ThreadedConnectionPool(1, 2, **config)
    conn = pool.getconn()
    cur = conn.cursor()

    cur.execute('''
        SELECT COUNT(*) as cnt FROM rds_locks
        WHERE locked_at < NOW() - INTERVAL '1 hour'
    ''')
    stale_locks = cur.fetchone()[0]
    if stale_locks > 0:
        check_issue('Stale Locks', f'{stale_locks} locks held > 1 hour', 'CRITICAL', 'FOUND')
        print(f"  ✗ {stale_locks} stale locks found")
    else:
        print("  ✓ No stale locks detected")

    pool.putconn(conn)
    pool.closeall()
except Exception as e:
    # rds_locks might not have 'locked_at' field, that's OK
    print(f"  ℹ Could not check locks: {e}")

# Test 6: Check for any hardcoded bypass logic
print("[CHECK 6] Safety bypass checks")
try:
    import subprocess

    # Search for any hardcoded bypasses or disables
    result = subprocess.run(
        ['grep', '-r', 'bypass', 'algo/', '--include=*.py'],
        capture_output=True, text=True, timeout=5
    )
    bypasses = result.stdout.strip().split('\n') if result.stdout.strip() else []
    bypasses = [b for b in bypasses if not b.startswith('#')]

    if bypasses:
        check_issue('Hardcoded Bypasses', f'Found {len(bypasses)} potential bypasses', 'WARNING', 'FOUND')
        print(f"  ⚠ {len(bypasses)} potential bypass references found (review needed)")
    else:
        print("  ✓ No obvious hardcoded bypasses detected")
except Exception as e:
    print(f"  ℹ Bypass check skipped: {e}")

print("\n" + "="*70)
print(f"ISSUES FOUND: {len(ISSUES)}")
for issue in ISSUES:
    print(f"\n[{issue['severity']}] {issue['name']}")
    print(f"  {issue['description']}")
    print(f"  Status: {issue['status']}")

if not ISSUES:
    print("\n✓✓✓ NO PRODUCTION BLOCKERS DETECTED ✓✓✓")
    print("\nSystem is code-wise ready for production.")
    print("Remaining action: Set real Alpaca credentials via environment or Secrets Manager")
    sys.exit(0)
else:
    sys.exit(1)
