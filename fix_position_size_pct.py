#!/usr/bin/env python3
"""Fix max_position_size_pct to 4.75% (per session 42 fix)."""

from utils.db.context import DatabaseContext

print("Fixing max_position_size_pct...")

print("\nBefore:")
with DatabaseContext("read") as cur:
    cur.execute("SELECT value FROM algo_config WHERE key='max_position_size_pct'")
    pct = cur.fetchone()[0]
    print(f"  max_position_size_pct: {pct}%")
    cur.execute("SELECT value FROM algo_config WHERE key='max_positions'")
    pos = cur.fetchone()[0]
    print(f"  max_positions: {pos}")
    print(f"  Math: {pos} * {pct}% = {float(pct)*float(pos)}% (should be 95%)")

print("\nUpdating...")
with DatabaseContext("write") as cur:
    cur.execute("UPDATE algo_config SET value='4.75' WHERE key='max_position_size_pct'")
    print(f"✓ Updated ({cur.rowcount} rows)")

print("\nAfter:")
with DatabaseContext("read") as cur:
    cur.execute("SELECT value FROM algo_config WHERE key='max_position_size_pct'")
    pct = cur.fetchone()[0]
    print(f"  max_position_size_pct: {pct}%")
    cur.execute("SELECT value FROM algo_config WHERE key='max_positions'")
    pos = cur.fetchone()[0]
    print(f"  max_positions: {pos}")
    print(f"  Math: {pos} * {pct}% = {float(pct)*float(pos)}% (should be 95%)")

if float(pct) * float(pos) == 95.0:
    print("\n✓ FIXED: Config math now correct")
else:
    print(f"\n✗ ISSUE: Math is {float(pct)*float(pos)}%, expected 95%")
