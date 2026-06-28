#!/usr/bin/env python3
"""
Migration 026: Add stale data detection threshold configuration.

Adds config key 'stale_loader_threshold_minutes' to allow tuning stale data
detection thresholds based on measured production loader execution times.
Default: 30 minutes (conservative, prevents false positives).
"""

from utils.db.context import DatabaseContext

DESCRIPTION = "Add stale data detection threshold configuration"

_NEW_CONFIGS = [
    (
        "stale_loader_threshold_minutes",
        "30",
        "int",
        "Stale loader threshold minutes (measured from production execution times)",
    ),
]


def up():
    with DatabaseContext("write") as cur:
        for key, value, value_type, description in _NEW_CONFIGS:
            cur.execute(
                """
                INSERT INTO algo_config (key, value, value_type, description, updated_by)
                VALUES (%s, %s, %s, %s, 'migration-026')
                ON CONFLICT (key) DO NOTHING
                """,
                (key, value, value_type, description),
            )


def down():
    with DatabaseContext("write") as cur:
        cur.execute("DELETE FROM algo_config WHERE updated_by = 'migration-026'")
