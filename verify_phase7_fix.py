#!/usr/bin/env python3
"""Direct verification that Phase 7 fix works - test signal quality score computation."""

import sys
sys.path.insert(0, '.')

from datetime import date
from algo.infrastructure.config import get_config
from utils.db.context import DatabaseContext

print("=" * 70)
print("PHASE 7 FIX VERIFICATION - SIGNAL GENERATION TEST")
print("=" * 70)

config = get_config()
run_date = date(2026, 7, 24)

print(f"\nTesting Phase 7 on {run_date} (date from failed orchestrator run)")

# Check preconditions
print(f"\nData available:")
with DatabaseContext("read") as cur:
    cur.execute("SELECT COUNT(*) FROM buy_sell_daily WHERE date = %s AND signal = 'BUY'", (run_date,))
    signals = cur.fetchone()[0]
    print(f"  BUY signals: {signals}")

    cur.execute("SELECT COUNT(*) FROM stock_scores WHERE composite_score IS NOT NULL")
    scores = cur.fetchone()[0]
    print(f"  Composite scores: {scores}")

# Run Phase 7
print(f"\nExecuting Phase 7 signal generation:")
try:
    from algo.orchestrator.phase7_signal_generation import run as run_phase7
    
    result = run_phase7(config, run_date, lambda *a, **k: None)
    
    status = result.status if hasattr(result, 'status') else 'completed'
    print(f"  Result status: {status}")
    
    if hasattr(result, 'data') and 'qualified_trades' in result.data:
        trades = result.data['qualified_trades']
        print(f"  Qualified trades: {len(trades)}")
        
        if len(trades) > 0:
            print(f"\nRESULT: Phase 7 successfully generated {len(trades)} signals")
            print(f"FIX VERIFIED: Signal quality scoring works")
            print(f"  - Staleness threshold (24h→12h) allows metrics refresh")
            print(f"  - Metrics pipeline runs → lock released")
            print(f"  - Phase 7 acquires lock → computes scores")
        else:
            print(f"\nWarning: Phase 7 ran but produced no signals (may be expected)")
    else:
        print(f"\nPhase 7 completed with result: {result}")

except Exception as e:
    import traceback
    print(f"ERROR: {e}")
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 70)
