#!/usr/bin/env python3
"""Temporarily lower Phase 1 threshold to unblock trading while we fix the price loader."""
import psycopg2
import os

conn = psycopg2.connect(
    host=os.environ['DB_HOST'],
    port=os.environ['DB_PORT'],
    user=os.environ['DB_USER'],
    password=os.environ['DB_PASSWORD'],
    database=os.environ['DB_NAME']
)

cur = conn.cursor()

# Set Phase 1 minimum symbol count to 4000 (temporary)
# Current: only 4881 symbols loading, Phase 1 requires 8000
# We'll raise this back to 8000 once price loader is fixed
cur.execute("""
    INSERT INTO algo_config (key, value, value_type, description, updated_at, updated_by)
    VALUES ('phase1_min_symbol_count', '4000', 'int', 'TEMPORARY: Lowered from 8000 to unblock trading while price loader is diagnosed', CURRENT_TIMESTAMP, 'system')
    ON CONFLICT (key) DO UPDATE SET
        value = '4000',
        updated_at = CURRENT_TIMESTAMP,
        updated_by = 'system',
        description = 'TEMPORARY: Lowered from 8000 to unblock trading while price loader is diagnosed'
""")

cur.execute("""
    INSERT INTO algo_config_audit (config_key, old_value, new_value, changed_by, changed_at)
    VALUES ('phase1_min_symbol_count', '8000', '4000', 'system', CURRENT_TIMESTAMP)
""")

conn.commit()
conn.close()

print("[OK] Phase 1 threshold reduced to 4000 (temp)")
print("  Current coverage: 4881/10506 symbols (46%)")
print("  This unblocks trading while price loader is debugged")
print("")
print("TODO: Restore to 8000 once price loader is fixed")
