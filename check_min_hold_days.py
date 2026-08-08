#!/usr/bin/env python3
from utils.db.context import DatabaseContext
from algo.infrastructure.config.main import AlgoConfig

print("Checking min_hold_days config...")

# Check database value
with DatabaseContext("read") as cur:
    cur.execute("SELECT value FROM algo_config WHERE key='min_hold_days'")
    row = cur.fetchone()
    db_val = row[0] if row else "NOT FOUND"
    print(f"Database: min_hold_days={db_val}")

# Check Python config
config = AlgoConfig()
config_val = config.get("min_hold_days")
print(f"AlgoConfig: min_hold_days={config_val}")

# Check default in schema
try:
    from algo.infrastructure.config_schema import CONFIG_SCHEMA
    schema_entry = CONFIG_SCHEMA.get("min_hold_days")
    if schema_entry:
        print(f"Schema: min_hold_days={schema_entry}")
    else:
        print("Schema: min_hold_days NOT FOUND")
except Exception as e:
    print(f"Schema check error: {e}")
