#!/usr/bin/env python3
"""Backfill NULL cognito_sub in trades and positions to owner's cognito_sub."""

from algo.config.credential_manager import get_algo_owner_cognito_sub
from utils.db import DatabaseContext

owner_cognito = get_algo_owner_cognito_sub()
print(f"Using cognito_sub: {owner_cognito}")

if not owner_cognito or owner_cognito == "":
    print("ERROR: Could not determine owner cognito_sub")
    exit(1)

with DatabaseContext() as cur:
    # Backfill algo_trades
    cur.execute("""
    UPDATE algo_trades
    SET cognito_sub = %s
    WHERE cognito_sub IS NULL
    """, (owner_cognito,))

    trades_updated = cur.rowcount
    print(f"Updated {trades_updated} trades with NULL cognito_sub")

    # Backfill algo_positions
    cur.execute("""
    UPDATE algo_positions
    SET cognito_sub = %s
    WHERE cognito_sub IS NULL
    """, (owner_cognito,))

    positions_updated = cur.rowcount
    print(f"Updated {positions_updated} positions with NULL cognito_sub")

    # Verify
    cur.execute("SELECT COUNT(*) FROM algo_trades WHERE cognito_sub IS NULL")
    null_trades = cur.fetchone()[0]
    print(f"\nRemaining trades with NULL cognito_sub: {null_trades}")

    cur.execute("SELECT COUNT(*) FROM algo_positions WHERE cognito_sub IS NULL")
    null_positions = cur.fetchone()[0]
    print(f"Remaining positions with NULL cognito_sub: {null_positions}")

    if null_trades == 0 and null_positions == 0:
        print("\n✓ All cognito_sub fields populated successfully")
    else:
        print("\n✗ Some cognito_sub fields still NULL")
        exit(1)
