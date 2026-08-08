#!/usr/bin/env python3
"""
Comprehensive system audit to find and document all issues before going live.
"""
import sys
import re
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))

print("="*80)
print("COMPREHENSIVE SYSTEM AUDIT")
print("="*80)

issues_found = []
fixes_verified = []

# 1. Check min_hold_days fix
print("\n[1/5] Checking min_hold_days fix...")
config_file = Path("algo/infrastructure/config_schema.py")
content = config_file.read_text()

# Look for the min_hold_days default
match = re.search(r'"min_hold_days":\s*\(\s*"int",\s*0,\s*365,\s*False,\s*(\d+)\s*\)', content)
if match:
    default_val = int(match.group(1))
    if default_val == 0:
        fixes_verified.append("min_hold_days default changed to 0 in config_schema.py")
    else:
        issues_found.append(f"[CRITICAL] min_hold_days default is {default_val}, should be 0")
else:
    issues_found.append("[ERROR] Could not find min_hold_days in config_schema.py")

# Check database config
try:
    import psycopg2
    from dotenv import load_dotenv
    env_file = Path('.env.local')
    if env_file.exists():
        load_dotenv(env_file)

    import os
    conn = psycopg2.connect(os.environ.get('DATABASE_URL', 'postgresql://postgres:postgres@localhost/algo'))
    with conn.cursor() as cur:
        cur.execute("SELECT value FROM algo_config WHERE key = 'min_hold_days'")
        result = cur.fetchone()
        if result:
            if result[0] == '0':
                fixes_verified.append("min_hold_days database config set to 0")
            else:
                issues_found.append(f"[CRITICAL] Database min_hold_days is {result[0]}, should be 0")
        else:
            fixes_verified.append("min_hold_days not in DB (uses default of 0)")
    conn.close()
except Exception as e:
    issues_found.append(f"[WARNING] Could not check database config: {e}")

# 2. Check exit engine is using config value
print("\n[2/5] Checking exit engine uses min_hold_days from config...")
exit_engine_file = Path("algo/trading/exit_engine.py")
exit_content = exit_engine_file.read_text()

if 'self.config.get("min_hold_days")' in exit_content and 'min_hold_days_check = int(min_hold_val)' in exit_content:
    fixes_verified.append("Exit engine uses config.get('min_hold_days') instead of hardcoding")
else:
    issues_found.append("[ERROR] Exit engine may not be using config value properly")

# 3. Check Phase 8 fixes
print("\n[3/5] Checking Phase 8 sizer fixes...")
phase8_file = Path("algo/orchestrator/phase8_entry_execution.py")
phase8_content = phase8_file.read_text()

# Check for Decimal conversion
if 'isinstance(portfolio_value, Decimal)' in phase8_content and 'Decimal(str(portfolio_value))' in phase8_content:
    fixes_verified.append("Phase 8 converts portfolio_value to Decimal for sizer")
else:
    issues_found.append("[WARNING] Phase 8 may not properly convert portfolio_value to Decimal")

# Check for exception tracking in skip reasons
if 'error_key = f\'error_{type(e).__name__}\'' in phase8_content:
    fixes_verified.append("Phase 8 tracks exceptions in skip_reason_counts")
else:
    issues_found.append("[WARNING] Phase 8 may not properly track exception errors")

# 4. Check for other potential issues
print("\n[4/5] Scanning for common bugs...")

# Check for hardcoded values that should be config
if 'max_positions' in exit_content or 'max_positions' in phase8_content:
    # These should be reading from config, not hardcoding
    if 'self.config.get("max_positions")' in exit_content:
        fixes_verified.append("Exit engine uses config for max_positions")
    if 'sizer_config["max_positions"]' in phase8_content or 'config.get("max_positions")' in phase8_content:
        fixes_verified.append("Phase 8 uses config for max_positions")

# Check position limit enforcement
if '15' in exit_content or '15' in phase8_content:
    # Could be an issue - should use config
    matches_config = False
    for line in exit_content.split('\n') + phase8_content.split('\n'):
        if '15' in line and 'max_positions' not in line and '0.15' not in line:
            if 'number 15' not in line and 'fifteen' not in line:
                issues_found.append(f"[WARNING] Found hardcoded '15' that might be position limit: {line.strip()[:60]}...")
                matches_config = True
                break

# 5. Check database integrity
print("\n[5/5] Checking database integrity...")
try:
    conn = psycopg2.connect(os.environ.get('DATABASE_URL', 'postgresql://postgres:postgres@localhost/algo'))
    with conn.cursor() as cur:
        # Check orphaned positions
        cur.execute("""
            SELECT COUNT(*) FROM algo_positions p
            WHERE status = 'open' AND NOT EXISTS (SELECT 1 FROM algo_trades t WHERE t.position_id = p.position_id)
        """)
        orphaned = cur.fetchone()[0]
        if orphaned == 0:
            fixes_verified.append("No orphaned positions found")
        else:
            issues_found.append(f"[ERROR] Found {orphaned} orphaned positions")

        # Check open positions match trades
        cur.execute("SELECT COUNT(*) FROM algo_positions WHERE status = 'open'")
        pos_count = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM algo_trades WHERE status = 'open'")
        trade_count = cur.fetchone()[0]

        if pos_count == trade_count:
            fixes_verified.append(f"Position/Trade match verified ({pos_count} each)")
        else:
            issues_found.append(f"[ERROR] Position count ({pos_count}) != Trade count ({trade_count})")

    conn.close()
except Exception as e:
    issues_found.append(f"[WARNING] Database integrity check failed: {e}")

# Print summary
print("\n" + "="*80)
print("AUDIT RESULTS")
print("="*80)

print(f"\nFixes Verified: {len(fixes_verified)}")
for fix in fixes_verified:
    print(f"  ✓ {fix}")

if issues_found:
    print(f"\nIssues Found: {len(issues_found)}")
    for issue in issues_found:
        print(f"  ✗ {issue}")
else:
    print(f"\nIssues Found: 0")

print("\n" + "="*80)
if len(issues_found) == 0:
    print("STATUS: All critical issues fixed. System ready for next test run.")
    sys.exit(0)
else:
    print(f"STATUS: {len(issues_found)} issue(s) need attention before testing.")
    sys.exit(1)

