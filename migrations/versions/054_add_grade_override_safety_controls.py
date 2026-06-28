#!/usr/bin/env python3
"""
Migration 054: Add Grade Override Safety Controls

Adds explicit safeguards for min_swing_grade override feature:
1. grade_override_enabled: false (default) - must be explicitly enabled
2. grade_override_max_duration_minutes: 60 (default) - auto-reset after N minutes

These controls prevent accidental permanent bypass of grade filtering
and ensure override is time-bounded (resets at market close).
"""

from utils.db.context import DatabaseContext

DESCRIPTION = "Add grade override safety controls (explicit enable flag + duration limit)"

# New config keys for grade override safety
SAFETY_CONFIGS = [
    (
        "grade_override_enabled",
        "false",
        "bool",
        "SAFETY: Enable grade override (bypass). Must be explicitly set to true; auto-resets at market close",
    ),
    (
        "grade_override_max_duration_minutes",
        "60",
        "int",
        "SAFETY: Max duration in minutes override can stay active before triggering alert",
    ),
]


def up():
    """Add grade override safety config keys."""
    with DatabaseContext("write") as cur:
        for key, value, value_type, description in SAFETY_CONFIGS:
            cur.execute(
                """
                INSERT INTO algo_config (key, value, value_type, description, updated_by)
                VALUES (%s, %s, %s, %s, 'migration-054')
                ON CONFLICT (key) DO NOTHING
                """,
                (key, value, value_type, description),
            )

    return True


def down():
    """Remove grade override safety config keys (reversal)."""
    with DatabaseContext("write") as cur:
        for key, _, _, _ in SAFETY_CONFIGS:
            cur.execute(
                "DELETE FROM algo_config WHERE key = %s AND updated_by = 'migration-054'",
                (key,),
            )

    return True
