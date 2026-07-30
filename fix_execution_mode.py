#!/usr/bin/env python3
import os
from algo.infrastructure.config.db_config import get_connection_pool

pool = get_connection_pool()
con = pool.getconn()
cur = con.cursor()

try:
    # Check current value
    cur.execute("SELECT config_value FROM algo_config WHERE config_key = 'execution_mode'")
    result = cur.fetchone()
    print(f"Current execution_mode in DB: {result[0] if result else 'NOT FOUND'}")
    print(f"ORCHESTRATOR_EXECUTION_MODE env var: {os.environ.get('ORCHESTRATOR_EXECUTION_MODE', 'NOT SET')}")

    # Fix: Set both to consistent value
    cur.execute("UPDATE algo_config SET config_value = %s WHERE config_key = %s", ('paper', 'execution_mode'))
    con.commit()
    print("✓ Updated algo_config execution_mode to paper")

    # Verify
    cur.execute("SELECT config_value FROM algo_config WHERE config_key = 'execution_mode'")
    print(f"✓ Verified: {cur.fetchone()[0]}")
finally:
    pool.putconn(con)
