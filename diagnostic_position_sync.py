#!/usr/bin/env python3
"""Diagnose position synchronization and data integrity issues."""

import sys
import logging
from datetime import datetime, timedelta
logging.basicConfig(level=logging.ERROR)
sys.path.insert(0, '.')

from utils.db import DatabaseContext
from algo.infrastructure import AlgoConfig

config = AlgoConfig()

print("="*90)
print("POSITION DATA INTEGRITY DIAGNOSTIC")
print("="*90)

# 1. Check what positions should exist (from trades)
print("\n1. OPEN POSITIONS FROM TRADE DATA:")
print("-"*90)
with DatabaseContext('read') as cur:
    cur.execute('''
        SELECT symbol, SUM(quantity) as total_qty
        FROM algo_trades
        WHERE status IN ('filled', 'open', 'partially_filled')
        GROUP BY symbol
        HAVING SUM(quantity) > 0
        ORDER BY symbol
    ''')

    trade_positions = {}
    for symbol, qty in cur.fetchall():
        trade_positions[symbol] = qty
        print(f"  {symbol}: {qty:.2f} shares")

# 2. Check what's in algo_positions table
print("\n2. POSITIONS IN ALGO_POSITIONS TABLE:")
print("-"*90)
with DatabaseContext('read') as cur:
    cur.execute('''
        SELECT symbol, quantity, status
        FROM algo_positions
        WHERE status = 'open'
        ORDER BY symbol
    ''')

    db_positions = {}
    for symbol, qty, status in cur.fetchall():
        db_positions[symbol] = qty
        print(f"  {symbol}: {qty:.2f} shares ({status})")

    if not db_positions:
        print("  (NO OPEN POSITIONS FOUND)")

# 3. Compare
print("\n3. DISCREPANCIES:")
print("-"*90)
all_symbols = set(trade_positions.keys()) | set(db_positions.keys())

discrepancies = []
for symbol in sorted(all_symbols):
    trade_qty = trade_positions.get(symbol, 0)
    db_qty = db_positions.get(symbol, 0)

    if trade_qty != db_qty:
        discrepancies.append((symbol, trade_qty, db_qty))
        print(f"  {symbol}: Trades={trade_qty:.2f}, DB={db_qty:.2f} MISMATCH!")

if not discrepancies:
    print("  No discrepancies found - data is in sync")

# 4. Check if positions are being loaded correctly
print("\n4. POSITION SYNCHRONIZATION STATUS:")
print("-"*90)
with DatabaseContext('read') as cur:
    # Check if there's a position sync job
    cur.execute('''
        SELECT table_name, status, completion_pct, last_updated
        FROM data_loader_status
        WHERE table_name = 'algo_positions'
    ''')

    row = cur.fetchone()
    if row:
        table, status, pct, updated = row
        print(f"  Loader status: {status} ({pct}%)")
        print(f"  Last updated: {updated}")
    else:
        print("  No loader status found for algo_positions")

# 5. Check reconciliation status
print("\n5. RECONCILIATION STATUS (last 24h):")
print("-"*90)
with DatabaseContext('read') as cur:
    cur.execute('''
        SELECT reconciliation_date, status, positions_count, total_value, reconciliation_notes
        FROM algo_reconciliation_log
        WHERE reconciliation_date >= NOW() - INTERVAL '24 hours'
        ORDER BY reconciliation_date DESC
        LIMIT 3
    ''')

    for date, status, count, value, notes in cur.fetchall():
        print(f"  {date}: {status} | Positions={count} | Value=\${value:,.2f}")
        if notes:
            print(f"    Notes: {notes[:100]}")

print("\n" + "="*90)
if discrepancies:
    print(f"CRITICAL: Found {len(discrepancies)} position sync issues")
    print("RECOMMENDATION: Run position reconciliation/sync")
else:
    print("Position data is in sync")
print("="*90)
