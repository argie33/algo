#!/usr/bin/env python3
"""
Diagnose why Phase 6 didn't detect the triggered exit conditions.
"""

import os
import sys
from datetime import date as _date
from decimal import Decimal

os.environ['DB_NAME'] = 'stocks'
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.db.context import DatabaseContext

def check_exit_trigger_detection():
    """Verify what Phase 6 should see"""
    print("\n" + "="*80)
    print("DIAGNOSING: Exit Condition Detection")
    print("="*80)

    with DatabaseContext('read') as ctx:
        # Check the exact state Phase 6 would see

        print("\n[QUERY 1] Positions Phase 6 detects:")
        ctx.execute('''
        SELECT COUNT(*), COUNT(CASE WHEN position_value IS NULL THEN 1 END)
        FROM algo_positions WHERE status='open'
        ''')
        total, nulls = ctx.fetchone()
        print(f"  Total open: {total}")
        print(f"  With NULL position_value: {nulls}")

        # Check specifically the modified positions
        print("\n[QUERY 2] Positions we modified:")
        ctx.execute('''
        SELECT symbol, position_id, entry_price, current_price, stop_loss_price,
               (current_price - stop_loss_price) as diff
        FROM algo_positions
        WHERE symbol IN ('TPR', 'EAT')
        AND status = 'open'
        ''')

        rows = ctx.fetchall()
        for symbol, pos_id, entry, curr, stop, diff in rows:
            print(f"\n  {symbol}:")
            print(f"    Entry: ${float(entry):.2f}")
            print(f"    Current: ${float(curr):.2f}")
            print(f"    Stop loss: ${float(stop):.2f}")
            if diff:
                print(f"    Diff (curr - stop): ${float(diff):.2f}")
                if float(diff) < 0:
                    print(f"    ⚠️ STOP TRIGGERED (price below stop)")
                else:
                    print(f"    ✓ Stop not triggered (price above stop)")

        # Check the exit engine logic
        print("\n[QUERY 3] What ExitEngine would check:")
        ctx.execute('''
        SELECT
            symbol,
            position_id,
            entry_price,
            current_price,
            stop_loss_price,
            CASE
                WHEN current_price <= stop_loss_price THEN 'TRIGGERED'
                ELSE 'not triggered'
            END as stop_status
        FROM algo_positions
        WHERE status = 'open'
        ORDER BY symbol
        ''')

        positions = ctx.fetchall()
        triggered = 0
        for symbol, pos_id, entry, curr, stop, status in positions:
            if status == 'TRIGGERED':
                triggered += 1
                print(f"  {symbol}: {status}")

        if triggered == 0:
            print("  (no stops triggered)")

        print(f"\nTotal positions with triggered stops: {triggered}")

        # Check concentration
        print("\n[QUERY 4] Concentration calculation:")
        ctx.execute('''
        SELECT total_portfolio_value FROM algo_portfolio_snapshots
        WHERE snapshot_date <= %s
        ORDER BY snapshot_date DESC LIMIT 1
        ''', (_date.today(),))

        row = ctx.fetchone()
        if row:
            portfolio = float(row[0])
            max_allowed = portfolio * 0.06
            print(f"  Portfolio: ${portfolio:,.2f}")
            print(f"  Individual limit (6%): ${max_allowed:,.2f}")

            ctx.execute('''
            SELECT symbol, position_value
            FROM algo_positions
            WHERE status = 'open'
            AND position_value > %s
            ORDER BY position_value DESC
            ''', (Decimal(str(max_allowed)),))

            violations = ctx.fetchall()
            if violations:
                print(f"\n  Concentration violations ({len(violations)}):")
                for symbol, pos_value in violations:
                    pct = (float(pos_value) / portfolio) * 100
                    print(f"    {symbol}: ${float(pos_value):,.2f} ({pct:.2f}%) - EXCEEDS LIMIT")
            else:
                print(f"\n  No concentration violations")

def check_exit_engine_internals():
    """Check if ExitEngine logic would find these"""
    print("\n" + "="*80)
    print("CHECKING: ExitEngine Stop Loss Logic")
    print("="*80)

    try:
        from algo.trading import ExitEngine
        from algo.infrastructure.config import get_config

        config = get_config()
        engine = ExitEngine(config)

        print("\n[ExitEngine] Checking exits for", _date.today())

        # This is the internal method that checks stops
        try:
            exits, stops, errors, forced = engine.check_and_execute_exits(_date.today())
            print(f"  Exits: {exits}")
            print(f"  Stop-raises: {stops}")
            print(f"  Errors: {errors}")
            print(f"  Forced closes: {forced}")

            if exits > 0 or stops > 0:
                print("\n✓ ExitEngine found triggers!")
            else:
                print("\n⚠️ ExitEngine found NO triggers")

        except Exception as e:
            print(f"  ERROR calling check_and_execute_exits: {e}")

    except Exception as e:
        print(f"\nERROR: Could not test ExitEngine: {e}")

def main():
    print("\n" + "="*80)
    print("SESSION 20: Diagnosing Phase 6 Detection Issue")
    print("="*80)

    check_exit_trigger_detection()
    check_exit_engine_internals()

    print("\n" + "="*80)
    print("CONCLUSION")
    print("="*80)
    print("""
If Phase 6 reported "0 exits" but the database shows triggered conditions:
  → BUG: Phase 6 or ExitEngine is not detecting exit conditions
  → Need to check: exit trigger logic, price comparisons, database reads

If the database shows no triggered conditions:
  → The modified data wasn't committed or visible to Phase 6
  → Need to check: transaction isolation, connection state
    """)

if __name__ == "__main__":
    main()
