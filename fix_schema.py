#!/usr/bin/env python3
"""Fix the partial_exits_log column type"""
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

    # Check current column type
    cur.execute("""
        SELECT data_type FROM information_schema.columns
        WHERE table_name = 'algo_trades' AND column_name = 'partial_exits_log'
    """)
    result = cur.fetchone()
    if result:
        current_type = result[0]
        print(f"Current type: {current_type}")

        if current_type == 'jsonb':
            print("Changing partial_exits_log from JSONB to TEXT...")
            cur.execute("ALTER TABLE algo_trades ALTER COLUMN partial_exits_log TYPE TEXT;")
            conn.commit()
            print("✓ Column type changed successfully")
        else:
            print(f"Column is already {current_type}, no change needed")
    else:
        print("Column not found")

    cur.close()
    conn.close()
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
