#!/usr/bin/env python3
"""Check database schema for issues"""
from credential_manager import get_credential_manager
credential_manager = get_credential_manager()

import os
import psycopg2
from pathlib import Path
from dotenv import load_dotenv

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "user": os.getenv("DB_USER", "stocks"),
    "password": credential_manager.get_db_credentials()["password"],
    "database": os.getenv("DB_NAME", "stocks"),
}

try:
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()

    # Check stock_scores columns
    print("\n" + "="*80)
    print("STOCK_SCORES COLUMNS")
    print("="*80)
    cur.execute("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = 'stock_scores'
        ORDER BY ordinal_position
    """)
    cols = cur.fetchall()
    for col_name, col_type in cols:
        print(f"  {col_name:30s} {col_type}")

    # Check if table exists and has rows
    cur.execute("SELECT COUNT(*) FROM stock_scores")
    count = cur.fetchone()[0]
    print(f"\nRows in stock_scores: {count}")

    # Check swing_trader_scores
    print("\n" + "="*80)
    print("SWING_TRADER_SCORES COLUMNS")
    print("="*80)
    cur.execute("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = 'swing_trader_scores'
        ORDER BY ordinal_position
    """)
    cols = cur.fetchall()
    for col_name, col_type in cols:
        print(f"  {col_name:30s} {col_type}")

    cur.execute("SELECT COUNT(*) FROM swing_trader_scores")
    count = cur.fetchone()[0]
    print(f"\nRows in swing_trader_scores: {count}")

    conn.close()
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
