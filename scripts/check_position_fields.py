#!/usr/bin/env python3
"""Check which position fields are missing."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import psycopg2.extras

from utils.data_queries import get_open_positions
from utils.db.context import DatabaseContext

print("\n" + "="*80)
print("CHECK: Position required fields for API")
print("="*80)

with DatabaseContext() as db:
    cur = db.connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    positions = get_open_positions(cur)
    print(f"\nTotal positions: {len(positions)}")

    print("\nChecking required fields for each position:")
    print("  API requires: symbol, position_value, avg_entry_price, current_price")

    missing_count = 0
    for i, p in enumerate(positions):
        symbol = p.get("symbol")
        pos_val = p.get("position_value")
        entry = p.get("avg_entry_price")
        cur_price = p.get("current_price")

        is_valid = symbol and pos_val is not None and entry is not None and cur_price is not None

        if not is_valid:
            missing_count += 1
            print(f"\n  [{i+1}] {symbol}:")
            print(f"      symbol: {symbol}")
            print(f"      position_value: {pos_val} (type: {type(pos_val).__name__})")
            print(f"      avg_entry_price: {entry} (type: {type(entry).__name__})")
            print(f"      current_price: {cur_price} (type: {type(cur_price).__name__})")

    if missing_count == 0:
        print("\n  All positions have required fields!")
        print("\n  Sample positions:")
        for p in positions[:3]:
            print(f"    {p['symbol']:6} | entry=${p['avg_entry_price']:10.2f} | "
                  f"current=${p['current_price']:10.2f} | value=${p['position_value']:12.2f}")
    else:
        print(f"\n  {missing_count} positions missing required fields")

print("\n" + "="*80)
