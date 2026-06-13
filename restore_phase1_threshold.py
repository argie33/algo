#!/usr/bin/env python3
"""Restore Phase 1 threshold to 8000 now that price loader is fixed."""
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

# Restore Phase 1 minimum symbol count to 8000
cur.execute("""
    INSERT INTO algo_config (key, value, value_type, description, updated_at, updated_by)
    VALUES ('phase1_min_symbol_count', '8000', 'int', 'Minimum symbol count for healthy price data coverage', CURRENT_TIMESTAMP, 'system')
    ON CONFLICT (key) DO UPDATE SET
        value = '8000',
        updated_at = CURRENT_TIMESTAMP,
        updated_by = 'system',
        description = 'Minimum symbol count for healthy price data coverage'
""")

cur.execute("""
    INSERT INTO algo_config_audit (config_key, old_value, new_value, changed_by, changed_at)
    VALUES ('phase1_min_symbol_count', '4000', '8000', 'system', CURRENT_TIMESTAMP)
""")

conn.commit()
conn.close()

print("[OK] Phase 1 threshold restored to 8000")
print("  Price loader circuit breaker fix applied")
print("  System should now load all 10,506 symbols")
