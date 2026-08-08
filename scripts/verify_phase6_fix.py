#!/usr/bin/env python3
"""
Verification script for Phase 6 stop-raise persistence fix.
Tests that Phase 8 no longer resets current_stop_price after Phase 6 sets it.
"""

import os
import sys
os.environ['EXECUTION_MODE'] = 'paper'

from datetime import date as _date, timedelta
from decimal import Decimal
from algo.infrastructure import AlgoConfig
from algo.monitoring import PositionMonitor
from utils.db import DatabaseContext

def main():
    print("=" * 80)
    print("PHASE 6 STOP-RAISE PERSISTENCE VERIFICATION")
    print("=" * 80)
    print()

    config = AlgoConfig()

    # Step 1: Get Phase 3 recommendations
    print("[STEP 1] Generating Phase 3 position monitor recommendations...")
    monitoring_date = _date.today() - timedelta(days=1)

    try:
        monitor = PositionMonitor(config)
        recs = monitor.review_positions(monitoring_date)

        raise_stop_recs = [r for r in recs if r['action'] == 'RAISE_STOP']
        print(f"  Generated {len(raise_stop_recs)} RAISE_STOP recommendations")

        if not raise_stop_recs:
            print("  WARNING: No RAISE_STOP recommendations generated. This may indicate positions are not healthy enough.")
            return False

        for rec in raise_stop_recs[:3]:
            print(f"    - {rec['symbol']} (pos_id={rec['position_id']}): {rec['active_stop']:.2f} -> {rec['new_stop_recommended']:.2f}")
        if len(raise_stop_recs) > 3:
            print(f"    ... and {len(raise_stop_recs)-3} more")

    except Exception as e:
        print(f"  ERROR: Failed to generate recommendations: {e}")
        return False

    print()

    # Step 2: Compare with database
    print("[STEP 2] Comparing Phase 3 recommendations with current database state...")

    ctx = DatabaseContext()
    with ctx as cursor:
        cursor.execute('''
            SELECT id, symbol, current_stop_price
            FROM algo_positions
            WHERE status = 'open'
            ORDER BY id DESC
        ''')
        db_positions = {row[0]: (row[1], row[2]) for row in cursor.fetchall()}

    mismatches = 0
    for rec in raise_stop_recs:
        pos_id = int(rec['position_id'])
        recommended_stop = Decimal(str(rec['new_stop_recommended']))

        if pos_id in db_positions:
            symbol, actual_stop = db_positions[pos_id]
            actual_stop_decimal = Decimal(str(actual_stop)) if actual_stop else Decimal('0')

            # Allow small floating point differences
            diff = abs(recommended_stop - actual_stop_decimal)
            if diff > Decimal('0.01'):
                mismatches += 1
                print(f"  MISMATCH: {symbol} (pos_id={pos_id})")
                print(f"    Recommended: ${recommended_stop}")
                print(f"    Database:    ${actual_stop_decimal}")
                print(f"    Difference:  ${diff}")

    if mismatches == 0:
        print(f"  ✓ All {len(raise_stop_recs)} positions have current_stop_price matching Phase 3 recommendations")
        print()
        print("[VERIFICATION PASSED] Phase 6 stop-raises are persisting correctly!")
        return True
    else:
        print(f"  ✗ {mismatches}/{len(raise_stop_recs)} positions have outdated stops")
        print()
        print("[VERIFICATION FAILED] Stop-raises are NOT persisting to database")
        print("  This indicates Phase 8 may still be resetting current_stop_price")
        return False

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
