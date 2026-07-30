#!/usr/bin/env python3
"""Test exit execution specifically to understand Phase 6 behavior."""

import sys
import logging
from pathlib import Path
from datetime import datetime

# Set up logging
logging.basicConfig(level=logging.WARNING, format='%(levelname)s:%(name)s:%(message)s')

# Setup path and credentials
from utils.dotenv_loader import load_env_local
load_env_local()

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

try:
    from scripts.load_credentials import ensure_credentials_loaded
    ensure_credentials_loaded()
except Exception as e:
    logging.getLogger(__name__).warning(f"[CREDS] Could not load credentials: {e}")

# Now import and test
from algo.infrastructure.config.main import AlgoConfig
from utils.db.context import DatabaseContext

print("\n" + "="*70)
print("PHASE 6 EXIT EXECUTION DIAGNOSTICS")
print("="*70)

try:
    config = AlgoConfig()

    # Check what positions are in the database
    print("\n[1] Checking positions in database...")
    with DatabaseContext('read') as cur:
        cur.execute("""
        SELECT position_id, symbol, quantity, current_price, stop_loss_price,
               unrealized_pnl, status
        FROM algo_positions
        WHERE status = 'open'
        ORDER BY created_at DESC
        LIMIT 20
        """)
        positions = cur.fetchall()
        print(f"    Found {len(positions)} open positions:")
        for pos in positions:
            print(f"    - {pos[1]} ({pos[0][:12]}): qty={pos[2]}, price=${pos[3]}, stop=${pos[4]}, pnl=${pos[5]}, status={pos[6]}")

    # Check for any positions that should trigger exits
    print("\n[2] Checking positions below stop loss...")
    with DatabaseContext('read') as cur:
        cur.execute("""
        SELECT symbol, current_price, stop_loss_price, current_price <= stop_loss_price as below_stop
        FROM algo_positions
        WHERE status = 'open'
        AND current_price IS NOT NULL
        AND stop_loss_price IS NOT NULL
        AND current_price <= stop_loss_price
        """)
        below_stop = cur.fetchall()
        if below_stop:
            print(f"    WARNING: {len(below_stop)} positions below stop loss:")
            for row in below_stop:
                print(f"    - {row[0]}: price=${row[1]} <= stop=${row[2]}")
        else:
            print(f"    OK: No positions below stop loss")

    # Check for sector concentration exits
    print("\n[3] Checking sector concentration...")
    with DatabaseContext('read') as cur:
        cur.execute("""
        SELECT COUNT(*) as total_positions, SUM(position_value) as total_value
        FROM algo_positions
        WHERE status = 'open'
        """)
        result = cur.fetchone()
        total_positions = result[0]
        total_value = result[1]
        print(f"    Total: {total_positions} positions, ${total_value:,.0f}")

    # Check exit execution config
    print("\n[4] Checking exit execution configuration...")
    execution_mode = config.get("execution_mode", "unknown")
    alpaca_paper_trading = config.get("alpaca_paper_trading", "unknown")
    print(f"    execution_mode: {execution_mode}")
    print(f"    alpaca_paper_trading: {alpaca_paper_trading}")

    print("\n[5] Checking recent Phase 6 execution logs...")
    with DatabaseContext('read') as cur:
        cur.execute("""
        SELECT run_id, phase_results -> 'phase_6' -> 'summary' as phase6_summary
        FROM orchestrator_execution_log
        WHERE phase_results -> 'phase_6' IS NOT NULL
        AND overall_status IN ('ok', 'error', 'degraded')
        ORDER BY started_at DESC
        LIMIT 5
        """)
        logs = cur.fetchall()
        if logs:
            print(f"    Last 5 Phase 6 executions:")
            for run_id, summary in logs:
                print(f"    - {run_id}: {summary}")
        else:
            print(f"    No Phase 6 execution logs found")

    print("\n" + "="*70)
    print("DIAGNOSTICS COMPLETE")
    print("="*70)

except Exception as e:
    print(f"\n[ERROR] {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
