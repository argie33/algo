#!/usr/bin/env python3
"""
Migration 1143: URGENT - Restore phase1_min_coverage_pct from disabled value

CRITICAL ISSUE DETECTED (same bug class as migration 033):
phase1_min_coverage_pct is currently 10 in the database (updated_by='system',
2026-07-05, no algo_config_audit trail - set outside the governed config-change
path). The schema default (algo/infrastructure/config_schema.py,
algo/infrastructure/config/main.py) is 75.

Impact: Phase 1's price-coverage freshness gate (algo/orchestrator/
phase1_data_freshness.py) only halts if today's loaded symbol count is below
10% of the prior trading day's count. Confirmed live 2026-07-20: the price
loader stopped after ~9 minutes (08:55-09:05 ET) having loaded only 4,533 of
~10,400 usual symbols (43.6% coverage) and never resumed - Phase 1 still
logged this as "success" because 43.6% > 10%. The intended gate (75%) would
have correctly halted and surfaced the stalled loader instead of silently
running the rest of the day on half the stock universe.

This migration restores the safe default.
"""

from utils.db.context import DatabaseContext

DESCRIPTION = "URGENT: Restore phase1_min_coverage_pct from 10 to safe default 75"

KEY = "phase1_min_coverage_pct"
SAFE_VALUE = "75"
VALUE_TYPE = "int"


def up():
    """Restore phase1_min_coverage_pct to the safe default."""
    with DatabaseContext("write") as cur:
        cur.execute("SELECT value FROM algo_config WHERE key = %s", (KEY,))
        row = cur.fetchone()
        old_value = row[0] if row else None

        cur.execute(
            """
            INSERT INTO algo_config (key, value, value_type, updated_by)
            VALUES (%s, %s, %s, 'migration-1143')
            ON CONFLICT (key) DO UPDATE SET
                value = %s,
                updated_by = 'migration-1143',
                updated_at = CURRENT_TIMESTAMP
            """,
            (KEY, SAFE_VALUE, VALUE_TYPE, SAFE_VALUE),
        )

        cur.execute(
            """
            INSERT INTO algo_config_audit (config_key, old_value, new_value, changed_by, changed_at)
            VALUES (%s, %s, %s, 'migration-1143-safety-restore', CURRENT_TIMESTAMP)
            """,
            (KEY, old_value or "NULL", SAFE_VALUE),
        )


def down():
    """Rollback: restore the previous (unsafe) value, only if it still matches what we set."""
    with DatabaseContext("write") as cur:
        cur.execute(
            """
            UPDATE algo_config
            SET value = '10', updated_by = 'migration-1143-rollback'
            WHERE key = %s AND value = %s
            """,
            (KEY, SAFE_VALUE),
        )
