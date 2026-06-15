#!/usr/bin/env python3
"""
Migration 006: Lower min_trend_template_score from 7 to 6.

7/8 Minervini criteria was filtering 91% of T3 candidates (36/1472 passed).
Score 6 allows legitimate high-quality setups through while maintaining
quality floor. This updates an existing config row â€” ON CONFLICT DO NOTHING
in migration 005 means the previous seeding kept whatever value was inserted
first, so this migration explicitly overwrites the T3 threshold.
"""

from migrations.migration_helper import DatabaseContext

DESCRIPTION = "Lower min_trend_template_score from 7 to 6 for broader T3 signal capture"


def up():
    with DatabaseContext("write") as cur:
        # Use CAST comparison so '7.0' and '7' both match. Only lower the threshold
        # if current value is 7 or higher â€” never override a manual value below 6.
        cur.execute("""
            UPDATE algo_config
            SET value = '6', updated_by = 'migration-006'
            WHERE key = 'min_trend_template_score'
              AND CAST(value AS NUMERIC) >= 7
            """)


def down():
    with DatabaseContext("write") as cur:
        cur.execute("""
            UPDATE algo_config
            SET value = '7', updated_by = 'migration-006-rollback'
            WHERE key = 'min_trend_template_score' AND value = '6'
            """)
