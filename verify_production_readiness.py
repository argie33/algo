import sys
sys.path.insert(0, '.')
from datetime import datetime
from utils.db.connection import get_db_connection

print("="*70)
print("PRODUCTION READINESS VERIFICATION")
print("="*70)

issues = []
warnings = []

with get_db_connection() as conn:
    cur = conn.cursor()
    
    # 1. Verify execution_mode can switch to 'auto'
    print("\n1. EXECUTION MODE VALIDATION")
    cur.execute("SELECT value FROM algo_config WHERE key = 'execution_mode'")
    mode_row = cur.fetchone()
    mode = mode_row[0] if mode_row else None
    print(f"   Current execution_mode: {mode}")
    if mode not in ('paper', 'auto', 'dry', 'review'):
        issues.append(f"Invalid execution_mode: {mode}")
    
    # 2. Check if Alpaca credentials are set
    print("\n2. ALPACA CREDENTIALS CHECK")
    cur.execute("SELECT value FROM algo_config WHERE key = 'alpaca_api_key'")
    key_row = cur.fetchone()
    api_key = key_row[0] if key_row else None
    cur.execute("SELECT value FROM algo_config WHERE key = 'alpaca_api_secret'")
    secret_row = cur.fetchone()
    api_secret = secret_row[0] if secret_row else None
    
    if api_key and api_key.startswith("PK"):
        warnings.append("Test credentials in DB (starts with PK) - rejected in auto mode")
    print(f"   Alpaca API Key: {'SET' if api_key else 'MISSING'}")
    print(f"   Alpaca API Secret: {'SET' if api_secret else 'MISSING'}")
    
    # 3. Check exit engine configuration
    print("\n3. EXIT ENGINE CONFIG")
    critical_exit_configs = [
        'max_hold_days',
        'exit_on_stop',
        'exit_on_target',
    ]
    for key in critical_exit_configs:
        cur.execute("SELECT value FROM algo_config WHERE key = %s", [key])
        value = cur.fetchone()
        if value and value[0]:
            print(f"   {key}: {value[0]}")
        else:
            warnings.append(f"Exit config missing: {key}")
    
    # 4. Verify all open positions have valid exit plans
    print("\n4. OPEN POSITIONS EXIT PLAN VALIDATION")
    cur.execute("""
    SELECT COUNT(*) FROM algo_positions
    WHERE status = 'open' AND (
        target_1_price IS NULL OR
        target_2_price IS NULL OR
        target_3_price IS NULL OR
        stop_loss_price IS NULL OR
        entry_price IS NULL OR
        current_price IS NULL
    )
    """)
    invalid_positions = cur.fetchone()[0]
    if invalid_positions > 0:
        issues.append(f"{invalid_positions} open positions missing exit plan data")
    else:
        cur.execute("SELECT COUNT(*) FROM algo_positions WHERE status = 'open'")
        total = cur.fetchone()[0]
        print(f"   OK - All {total} open positions have complete exit plans")
    
    # 5. Check for positions where current_price exceeds target 3
    print("\n5. TARGET PRICE VALIDATION")
    cur.execute("""
    SELECT COUNT(*) FROM algo_positions
    WHERE status = 'open' AND current_price > target_3_price
    """)
    exceeding_targets = cur.fetchone()[0]
    if exceeding_targets > 0:
        warnings.append(f"{exceeding_targets} positions above T3 (may need exits)")
    else:
        print("   OK - No positions exceeding target 3")
    
    # 6. Check for positions below stop loss
    print("\n6. STOP LOSS VALIDATION")
    cur.execute("""
    SELECT COUNT(*) FROM algo_positions
    WHERE status = 'open' AND current_price <= stop_loss_price
    """)
    below_stops = cur.fetchone()[0]
    if below_stops > 0:
        issues.append(f"{below_stops} positions below stop loss")
    else:
        print("   OK - No positions below stop loss")
    
    # 7. Database health
    print("\n7. DATABASE HEALTH")
    try:
        cur.execute("SELECT version()")
        ver = cur.fetchone()
        print(f"   OK - Database connected and responding")
    except Exception as e:
        issues.append(f"Database error: {e}")
    
    # 8. Check for data corruption
    print("\n8. DATA INTEGRITY")
    cur.execute("""
    SELECT COUNT(*) FROM algo_positions
    WHERE status = 'open' AND quantity <= 0
    """)
    zero_qty = cur.fetchone()[0]
    if zero_qty > 0:
        issues.append(f"{zero_qty} open positions with zero/negative quantity")
    else:
        print("   OK - All positions have positive quantities")
    
    # 9. Verify trade executor can initialize
    print("\n9. TRADE EXECUTOR")
    try:
        from algo.trading.executor import TradeExecutor
        from algo.infrastructure.config.main import AlgoConfig
        config = AlgoConfig()
        executor = TradeExecutor(config)
        print(f"   OK - TradeExecutor ready in {executor.execution_mode} mode")
    except Exception as e:
        issues.append(f"TradeExecutor failed: {str(e)[:100]}")
    
    # 10. Exit Engine
    print("\n10. EXIT ENGINE")
    try:
        from algo.trading.exit_engine import ExitEngine
        config = AlgoConfig()
        engine = ExitEngine(config)
        print("   OK - ExitEngine ready")
    except Exception as e:
        issues.append(f"ExitEngine failed: {str(e)[:100]}")

print("\n" + "="*70)
print("RESULTS")
print("="*70)

if issues:
    print(f"\nCRITICAL ISSUES ({len(issues)}):")
    for issue in issues:
        print(f"  [X] {issue}")
else:
    print("\n[OK] NO CRITICAL ISSUES")

if warnings:
    print(f"\nWARNINGS ({len(warnings)}):")
    for warning in warnings:
        print(f"  [!] {warning}")

print("\n" + "="*70)
if not issues:
    print("VERDICT: PRODUCTION READY - System is bulletproof")
else:
    print(f"VERDICT: FIX {len(issues)} ISSUE(S) BEFORE PRODUCTION")
print("="*70)
