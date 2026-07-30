#!/usr/bin/env python3
import os
import psycopg2

# Get DB connection from environment
db_url = os.environ.get('DATABASE_URL')
if not db_url:
    print("ERROR: DATABASE_URL not set")
    exit(1)

con = psycopg2.connect(db_url)
cur = con.cursor()

try:
    # Check current value
    cur.execute("SELECT value FROM algo_config WHERE key = 'execution_mode'")
    result = cur.fetchone()
    print(f"Current execution_mode in DB: {result[0] if result else 'NOT FOUND'}")
    print(f"ORCHESTRATOR_EXECUTION_MODE env var: {os.environ.get('ORCHESTRATOR_EXECUTION_MODE', 'NOT SET')}")

    # Fix: Set both to consistent value
    cur.execute("UPDATE algo_config SET value = %s WHERE key = %s", ('paper', 'execution_mode'))
    con.commit()
    print("✓ Updated algo_config execution_mode to paper")

    # Verify
    cur.execute("SELECT value FROM algo_config WHERE key = 'execution_mode'")
    print(f"✓ Verified: {cur.fetchone()[0]}")
finally:
    cur.close()
    con.close()
