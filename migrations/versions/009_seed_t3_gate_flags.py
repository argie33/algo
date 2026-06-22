#!/usr/bin/env python3
"""
Migration 009: Seed T3 configurable gate flags into algo_config.

rs_slope_gate_enabled and volume_decay_gate_enabled were added to filter_tier3_trend.py
to allow softening the RS-slope and volume-decay hard gates during strong market regimes
without a code deploy. Default: both True (gates on, same behavior as before).
ON CONFLICT DO NOTHING keeps any manually-set DB value.
"""

from utils.db.context import DatabaseContext

DESCRIPTION = "Seed rs_slope_gate_enabled and volume_decay_gate_enabled into algo_config"

_NEW_KEYS = [
    (
        "rs_slope_gate_enabled",
        "true",
        "bool",
        "Hard-gate T3 on RS line trending up (set false during strong SPY runs)",
    ),
    (
        "volume_decay_gate_enabled",
        "true",
        "bool",
        "Hard-gate T3 on volume decay into breakout (set false to soften)",
    ),
]


def up():
    with DatabaseContext("write") as cur:
        for key, value, value_type, description in _NEW_KEYS:
            cur.execute(
                """
                INSERT INTO algo_config (key, value, value_type, description, updated_by)
                VALUES (%s, %s, %s, %s, 'migration-009')
                ON CONFLICT (key) DO NOTHING
                """,
                (key, value, value_type, description),
            )


def down():
    with DatabaseContext("write") as cur:
        cur.execute("DELETE FROM algo_config WHERE updated_by = 'migration-009'")
