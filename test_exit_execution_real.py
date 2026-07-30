#!/usr/bin/env python3
"""Test exit execution with real position data to find issues."""

import sys
import logging
from pathlib import Path
from datetime import date as _date

logging.basicConfig(level=logging.WARNING, format='%(levelname)s:%(message)s')

# Setup
from utils.dotenv_loader import load_env_local
load_env_local()

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

try:
    from scripts.load_credentials import ensure_credentials_loaded
    ensure_credentials_loaded()
except Exception:
    pass

from algo.infrastructure.config.main import AlgoConfig
from algo.reporting import AlertManager
from utils.db.context import DatabaseContext

print("\n" + "="*80)
print("TESTING EXIT EXECUTION WITH REAL DATA")
print("="*80)

try:
    config = AlgoConfig()

    # Get position recommendations from position monitor
    print("\n[1] Getting position monitoring recommendations...")
    with DatabaseContext('read') as cur:
        cur.execute("""
        SELECT COUNT(*) FROM algo_positions WHERE status = 'open'
        """)
        open_count = cur.fetchone()[0]
        print(f"  Open positions: {open_count}")

        if open_count == 0:
            print("  [SKIP] Cannot test exit execution without open positions")
            sys.exit(0)

        # Check if any positions are below stop loss
        cur.execute("""
        SELECT symbol, current_price, stop_loss_price, unrealized_pnl
        FROM algo_positions
        WHERE status = 'open'
        ORDER BY unrealized_pnl_pct ASC
        """)
        positions = cur.fetchall()
        print(f"\n  Position summary (worst P&L first):")
        for sym, cur_price, stop, pnl in positions[:5]:
            print(f"    {sym}: price=${cur_price:.2f}, stop=${stop:.2f}, P&L=${pnl:.2f}")

    # Get position recommendations (simulate phase 3)
    print("\n[2] Simulating position monitor...")
    from algo.monitoring.position_monitor import PositionMonitor

    monitor = PositionMonitor(config)
    try:
        recs = monitor.review_positions(_date.today())
        print(f"  Recommendations generated: {len(recs)}")

        if len(recs) > 0:
            early_exits = len([r for r in recs if r.get('action') == 'EARLY_EXIT'])
            stop_raises = len([r for r in recs if r.get('action') == 'RAISE_STOP'])
            fails = len([r for r in recs if r.get('action') == 'FAILED_VALIDATION'])
            print(f"    - Early exits: {early_exits}")
            print(f"    - Stop raises: {stop_raises}")
            print(f"    - Validation failures: {fails}")

            if early_exits > 0:
                print(f"\n  Positions for early exit:")
                for r in recs:
                    if r.get('action') == 'EARLY_EXIT':
                        print(f"    {r['symbol']}: {r.get('action_reason')}")
    except Exception as e:
        print(f"  [ERROR] Position monitor failed: {e}")
        recs = []

    # Try to run Phase 6
    print("\n[3] Testing Phase 6 exit execution (dry-run)...")
    try:
        from algo.orchestrator.phase6_exit_execution import run as phase6_run

        alerts = AlertManager(config)
        def log_phase_result(phase_num, name, status, summary):
            print(f"  Phase result: {status} - {summary[:100]}")

        # Phase 5 would provide exposure actions - for now, empty list
        exposure_actions = []

        result = phase6_run(
            config=config,
            run_date=_date.today(),
            dry_run=True,
            alerts=alerts,
            verbose=True,
            log_phase_result_fn=log_phase_result,
            position_recs=recs,
            exposure_actions=exposure_actions
        )

        print(f"\n  Phase 6 result:")
        print(f"    Status: {result.status}")
        print(f"    Summary: {result.summary[:150]}")

        if not result.success:
            print(f"    [ERROR] Phase 6 failed!")
            if result.error:
                print(f"    Error: {result.error}")
    except Exception as e:
        print(f"  [ERROR] Phase 6 failed: {e}")
        import traceback
        traceback.print_exc()

    print("\n[4] Checking for data integrity issues...")
    with DatabaseContext('read') as cur:
        # Check if positions with NULL trade_ids can be exited
        cur.execute("""
        SELECT COUNT(*) FROM algo_positions
        WHERE status = 'open'
        AND (trade_ids_arr IS NULL OR array_length(trade_ids_arr, 1) IS NULL)
        """)
        no_trades = cur.fetchone()[0]
        if no_trades > 0:
            print(f"  [WARNING] {no_trades} positions have no trade_ids - cannot exit!")

        # Check for positions with NULL prices
        cur.execute("""
        SELECT COUNT(*) FROM algo_positions
        WHERE status = 'open'
        AND current_price IS NULL
        """)
        no_prices = cur.fetchone()[0]
        if no_prices > 0:
            print(f"  [WARNING] {no_prices} positions have NULL prices - cannot calculate P&L!")

        if no_trades == 0 and no_prices == 0:
            print(f"  [OK] All open positions have trade_ids and prices")

    print("\n" + "="*80)
    print("EXIT EXECUTION TEST COMPLETE")
    print("="*80)

except Exception as e:
    print(f"\n[CRITICAL] Test failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
