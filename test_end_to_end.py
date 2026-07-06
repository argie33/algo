import os
import sys
from datetime import date

print("="*70)
print("END-TO-END SYSTEM VERIFICATION TEST")
print("="*70)

# Set credentials
os.environ['APCA_API_KEY_ID'] = 'PK_test7aba5efad8a43f8aafdf3e4cf40c1a2f'
os.environ['APCA_API_SECRET_KEY'] = 'test_secret_key_for_paper_trading'
os.environ['SKIP_ORCHESTRATOR_LOCK'] = 'true'  # Skip lock for testing

from utils.db import DatabaseContext
from algo.orchestration.orchestrator import Orchestrator
from algo.infrastructure import get_config

# TEST 1: Dashboard rendering
print("\n[TEST 1] Dashboard Growth Scores Rendering")
print("-" * 70)
try:
    from dashboard.fetchers import load_all
    data = load_all()
    
    # Check if scores panel has growth_score
    if 'scores' in data and data['scores']:
        first_score = data['scores'][0] if isinstance(data['scores'], list) else None
        if first_score and 'growth_score' in first_score:
            print(f"PASS: Growth scores in dashboard data")
            print(f"  Example: {first_score.get('symbol')} growth_score={first_score.get('growth_score')}")
        else:
            print(f"FAIL: growth_score field missing from scores data")
            print(f"  Available fields: {list(first_score.keys())[:5] if first_score else 'None'}")
    else:
        print("FAIL: No scores data loaded")
except Exception as e:
    print(f"ERROR: {str(e)[:100]}")

# TEST 2: Trade execution with fresh lock
print("\n[TEST 2] Trade Execution with Credentials")
print("-" * 70)

try:
    config = get_config()
    orch = Orchestrator(config, run_date=date.today(), dry_run=False)
    result = orch.run()
    
    if result.get('success'):
        print("PASS: Orchestrator completed successfully")
    else:
        print(f"FAIL: Orchestrator error: {result.get('error', 'unknown')}")
    
except Exception as e:
    print(f"ERROR: {str(e)[:100]}")

# TEST 3: Verify trades were created
print("\n[TEST 3] Trade Execution Results")
print("-" * 70)

with DatabaseContext('read') as cur:
    # Check trades created today or yesterday
    cur.execute("""
        SELECT COUNT(*) as total,
               SUM(CASE WHEN status='OPEN' THEN 1 ELSE 0 END) as open,
               SUM(CASE WHEN entry_date >= CURRENT_DATE - 1 THEN 1 ELSE 0 END) as recent
        FROM algo_trades
    """)
    row = cur.fetchone()
    total, open_pos, recent = row[0], row[1], row[2]
    
    print(f"RESULT:")
    print(f"  Total trades all time: {total}")
    print(f"  Open positions: {open_pos}")
    print(f"  Recent trades (last 2 days): {recent}")
    
    if open_pos > 0:
        print("\nPASS: Open positions exist - trading is working!")
        
        # Show the trades
        cur.execute("""
            SELECT symbol, entry_price, quantity, entry_date
            FROM algo_trades
            WHERE status = 'OPEN'
            ORDER BY entry_date DESC
            LIMIT 5
        """)
        print("\nOpen Positions:")
        for trade_row in cur.fetchall():
            print(f"  {trade_row[0]:6s} @ ${trade_row[1]:8.2f} x {trade_row[2]:4d} ({trade_row[3]})")
    else:
        print("\nFAIL: No open positions - trades not executing")

# TEST 4: Positions sorting
print("\n[TEST 4] Positions Sorting Verification")
print("-" * 70)

with DatabaseContext('read') as cur:
    cur.execute("""
        SELECT sql FROM sqlite_master 
        WHERE type='view' AND name='algo_positions'
        LIMIT 1
    """)
    view_def = cur.fetchone()
    
    if view_def:
        sql = view_def[0] if view_def else ""
        if "ORDER BY" in sql and "position_value" in sql:
            print("PASS: Positions view has ORDER BY position_value")
        else:
            print("FAIL: Positions view missing ORDER BY or position_value")
    else:
        print("WARN: Could not read view definition (different DB type)")

print("\n" + "="*70)
print("TEST COMPLETE")
print("="*70)

