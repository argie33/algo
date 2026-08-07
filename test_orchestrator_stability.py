#!/usr/bin/env python3
"""
Test script to verify orchestrator stability and find remaining bugs.
Tests for: duplicate positions, false concentration violations, data integrity.
"""

import os
import sys
from datetime import date as _date

os.environ['DB_NAME'] = 'stocks'
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.db.context import DatabaseContext

def test_data_integrity():
    """Test for data corruption patterns"""

    print("\n" + "="*80)
    print("INTEGRITY TEST: Check for data corruption")
    print("="*80)

    with DatabaseContext('read') as ctx:
        # Test 1: Check for duplicate positions (same symbol, same status)
        ctx.execute('''
        SELECT symbol, status, COUNT(*) as cnt
        FROM algo_positions
        GROUP BY symbol, status
        HAVING COUNT(*) > 1
        ORDER BY cnt DESC
        ''')

        duplicates = ctx.fetchall()
        if duplicates:
            print("\nERROR: Found duplicate positions:")
            for symbol, status, count in duplicates:
                print(f"  {symbol}: {count} {status} positions (should be 1 max)")
            return False
        print("\nOK: No duplicate positions found")

        # Test 2: Check for positions with orphaned trade references
        ctx.execute('''
        SELECT ap.symbol, ap.position_id, ap.trade_ids_arr, COUNT(t.trade_id) as matched_trades
        FROM algo_positions ap
        LEFT JOIN algo_trades t ON t.trade_id = ANY(ap.trade_ids_arr)
        WHERE ap.status = 'open' AND ap.trade_ids_arr IS NOT NULL
        GROUP BY ap.symbol, ap.position_id, ap.trade_ids_arr
        HAVING COUNT(t.trade_id) = 0
        ''')

        orphaned = ctx.fetchall()
        if orphaned:
            print("\nERROR: Found positions with orphaned trade references:")
            for symbol, pos_id, trade_ids, count in orphaned:
                print(f"  {symbol} (pos={pos_id[:8]}...): trade_ids_arr={trade_ids} but no matching trades")
            return False
        print("OK: No orphaned trade references found")

        # Test 3: Check for trades without matching positions
        ctx.execute('''
        SELECT t.symbol, t.trade_id, t.position_id, COUNT(ap.id) as matching_positions
        FROM algo_trades t
        LEFT JOIN algo_positions ap ON ap.position_id = t.position_id
        WHERE t.status = 'open'
        GROUP BY t.symbol, t.trade_id, t.position_id
        HAVING COUNT(ap.id) = 0
        ''')

        unmatched_trades = ctx.fetchall()
        if unmatched_trades:
            print("\nERROR: Found open trades without matching positions:")
            for symbol, trade_id, pos_id, count in unmatched_trades:
                print(f"  {symbol} trade={trade_id} position_id={pos_id}: no matching position")
            return False
        print("OK: All open trades have matching positions")

        # Test 4: Verify position quantities are positive
        ctx.execute('''
        SELECT symbol, position_id, quantity FROM algo_positions
        WHERE quantity <= 0
        ''')

        bad_quantities = ctx.fetchall()
        if bad_quantities:
            print("\nERROR: Found positions with non-positive quantities:")
            for symbol, pos_id, qty in bad_quantities:
                print(f"  {symbol}: qty={qty} (should be > 0)")
            return False
        print("OK: All positions have positive quantities")

        # Test 5: Verify position entry prices are set
        ctx.execute('''
        SELECT symbol, position_id, entry_price FROM algo_positions
        WHERE entry_price IS NULL OR entry_price <= 0
        ''')

        bad_prices = ctx.fetchall()
        if bad_prices:
            print("\nERROR: Found positions with invalid entry prices:")
            for symbol, pos_id, price in bad_prices:
                print(f"  {symbol}: entry_price={price} (should be > 0)")
            return False
        print("OK: All positions have valid entry prices")

    return True

def test_concentration_logic():
    """Test concentration calculation logic"""

    print("\n" + "="*80)
    print("CONCENTRATION TEST: Verify concentration calculations")
    print("="*80)

    with DatabaseContext('read') as ctx:
        # Get portfolio snapshot
        ctx.execute('''
        SELECT snapshot_date, total_portfolio_value
        FROM algo_portfolio_snapshots
        ORDER BY snapshot_date DESC LIMIT 1
        ''')

        snapshot_row = ctx.fetchone()
        if not snapshot_row:
            print("\nWARNING: No portfolio snapshot available, skipping concentration test")
            return True

        snapshot_date, portfolio_value = snapshot_row
        print(f"\nUsing portfolio snapshot from {snapshot_date}: ${float(portfolio_value):,.2f}")

        if float(portfolio_value) <= 0:
            print("ERROR: Portfolio value is invalid (must be > 0)")
            return False

        # Check each position's concentration
        ctx.execute('''
        SELECT symbol, position_id, position_value, status
        FROM algo_positions
        WHERE status = 'open'
        ORDER BY symbol
        ''')

        positions = ctx.fetchall()
        print(f"\nChecking {len(positions)} open positions:")

        for symbol, pos_id, pos_value, status in positions:
            if pos_value is None or float(pos_value) <= 0:
                print(f"ERROR: {symbol} has invalid position_value={pos_value}")
                return False

            pct = (float(pos_value) / float(portfolio_value)) * 100
            max_pct = 6.0  # From config

            if pct > max_pct:
                print(f"  WARNING: {symbol}: {pct:.1f}% (exceeds {max_pct}% limit)")
            else:
                print(f"  OK: {symbol}: {pct:.1f}% (within {max_pct}% limit)")

    return True

def test_position_sync():
    """Test position_sync logic"""

    print("\n" + "="*80)
    print("POSITION_SYNC TEST: Verify sync logic correctness")
    print("="*80)

    with DatabaseContext('read') as ctx:
        # Verify every open position has at least one trade
        ctx.execute('''
        SELECT ap.symbol, COUNT(t.trade_id) as trade_count
        FROM algo_positions ap
        LEFT JOIN algo_trades t ON t.position_id = ap.position_id
        WHERE ap.status = 'open'
        GROUP BY ap.symbol
        HAVING COUNT(t.trade_id) = 0
        ''')

        orphaned = ctx.fetchall()
        if orphaned:
            print("\nERROR: Found open positions with no trades:")
            for symbol, count in orphaned:
                print(f"  {symbol}: {count} trades")
            return False
        print("\nOK: All open positions have at least one trade")

        # Verify position quantities match sum of trade quantities
        ctx.execute('''
        SELECT ap.symbol, ap.quantity as position_qty,
               COALESCE(SUM(t.quantity), 0) as trade_qty,
               ABS(ap.quantity - COALESCE(SUM(t.quantity), 0)) as diff
        FROM algo_positions ap
        LEFT JOIN algo_trades t ON t.position_id = ap.position_id
        WHERE ap.status = 'open'
        GROUP BY ap.id, ap.symbol, ap.quantity
        HAVING ABS(ap.quantity - COALESCE(SUM(t.quantity), 0)) > 0.01
        ''')

        mismatches = ctx.fetchall()
        if mismatches:
            print("\nERROR: Found position/trade quantity mismatches:")
            for symbol, pos_qty, trade_qty, diff in mismatches:
                print(f"  {symbol}: position={pos_qty}, trades={trade_qty}, diff={diff}")
            return False
        print("OK: All position quantities match trade sums")

    return True

if __name__ == '__main__':
    print("\n" + "="*80)
    print("ORCHESTRATOR STABILITY TESTS")
    print("="*80)

    all_pass = True

    all_pass &= test_data_integrity()
    all_pass &= test_concentration_logic()
    all_pass &= test_position_sync()

    print("\n" + "="*80)
    if all_pass:
        print("ALL TESTS PASSED!")
    else:
        print("SOME TESTS FAILED - System needs fixes")
    print("="*80 + "\n")

    sys.exit(0 if all_pass else 1)
