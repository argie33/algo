#!/usr/bin/env python3
"""Apply missing quarterly metrics migrations to local database."""

import os
os.environ.setdefault("LOCAL_MODE", "true")
os.environ.setdefault("ENVIRONMENT", "development")

from utils.dotenv_loader import load_env_local
load_env_local()

from utils.db.context import DatabaseContext

migrations = [
    # growth_metrics quarterly columns
    "ALTER TABLE growth_metrics ADD COLUMN IF NOT EXISTS consecutive_positive_quarters INTEGER",
    "ALTER TABLE growth_metrics ADD COLUMN IF NOT EXISTS earnings_growth_4q_avg NUMERIC(10, 2)",
    "ALTER TABLE growth_metrics ADD COLUMN IF NOT EXISTS quarterly_growth_momentum NUMERIC(10, 2)",
    "ALTER TABLE growth_metrics ADD COLUMN IF NOT EXISTS eps_growth_stability NUMERIC(10, 2)",
    "ALTER TABLE growth_metrics ADD COLUMN IF NOT EXISTS consecutive_positive_quarters_unavailable_reason VARCHAR(255)",
    "ALTER TABLE growth_metrics ADD COLUMN IF NOT EXISTS earnings_growth_4q_avg_unavailable_reason VARCHAR(255)",
    "ALTER TABLE growth_metrics ADD COLUMN IF NOT EXISTS eps_growth_stability_unavailable_reason VARCHAR(255)",

    # quality_metrics quarterly columns
    "ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS consecutive_positive_quarters INTEGER",
    "ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS earnings_growth_4q_avg NUMERIC(10, 2)",
    "ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS eps_growth_stability NUMERIC(10, 2)",
    "ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS consecutive_positive_quarters_unavailable_reason VARCHAR(255)",
    "ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS earnings_growth_4q_avg_unavailable_reason VARCHAR(255)",
    "ALTER TABLE quality_metrics ADD COLUMN IF NOT EXISTS eps_growth_stability_unavailable_reason VARCHAR(255)",
]

with DatabaseContext("write") as cur:
    for migration in migrations:
        try:
            cur.execute(migration)
            print(f"[OK] {migration.split('ADD COLUMN')[1][:60].strip()}")
        except Exception as e:
            print(f"[FAIL] {migration}: {e}")

print("\nMigrations applied successfully!")
