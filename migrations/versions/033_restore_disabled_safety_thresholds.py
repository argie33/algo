#!/usr/bin/env python3
"""
Migration 033: URGENT - Restore disabled safety thresholds from zero

CRITICAL ISSUE DETECTED:
The following safety thresholds are currently set to ZERO in the database,
which disables all entry quality gates and earnings protection:

Current (DANGEROUS) State:
- min_signal_quality_score: 0 (should be 60)
- min_swing_score: 0.0 (should be 55.0)
- min_completeness_score: 0 (should be 70)
- earnings_blackout_days_before: 0 (should be 7)
- earnings_blackout_days_after: 0 (should be 3)
- min_avg_daily_dollar_volume: 1 (should be 500000)

Impact: System will trade ANY stock regardless of signal quality, data completeness,
or proximity to earnings announcements. This creates:
- High whipsaw rate from weak signals
- Gap risk from earnings surprises (uncontrolled stop-loss blowups)
- Position sizing errors from incomplete data (missing ATR/MA)

This migration restores safe defaults immediately.
"""

from migrations.migration_helper import DatabaseContext


DESCRIPTION = "URGENT: Restore safety thresholds from zero to safe defaults"

# Safe default values (matching AlgoConfig.DEFAULTS)
SAFE_DEFAULTS = [
    ("min_signal_quality_score", "60", "int"),
    ("min_swing_score", "55.0", "float"),
    ("min_completeness_score", "70", "int"),
    ("earnings_blackout_days_before", "7", "int"),
    ("earnings_blackout_days_after", "3", "int"),
    ("min_avg_daily_dollar_volume", "500000", "float"),
]


def up():
    """Restore all safety thresholds to safe defaults."""
    with DatabaseContext("write") as cur:
        for key, safe_value, value_type in SAFE_DEFAULTS:
            # Get current value for audit
            cur.execute(
                "SELECT value FROM algo_config WHERE key = %s",
                (key,)
            )
            row = cur.fetchone()
            old_value = row[0] if row else None

            # Update to safe value
            cur.execute(
                """
                INSERT INTO algo_config (key, value, value_type, updated_by)
                VALUES (%s, %s, %s, 'migration-033')
                ON CONFLICT (key) DO UPDATE SET
                    value = %s,
                    updated_by = 'migration-033',
                    updated_at = CURRENT_TIMESTAMP
                """,
                (key, safe_value, value_type, safe_value),
            )

            # Audit the restoration
            cur.execute(
                """
                INSERT INTO algo_config_audit (config_key, old_value, new_value, changed_by, changed_at)
                VALUES (%s, %s, %s, 'migration-033-safety-restore', CURRENT_TIMESTAMP)
                """,
                (key, old_value or "NULL", safe_value),
            )


def down():
    """Rollback: restore previous zero values (only if absolutely necessary)."""
    with DatabaseContext("write") as cur:
        # Only revert if they match what we just set (safety check)
        for key, safe_value, _ in SAFE_DEFAULTS:
            cur.execute(
                """
                UPDATE algo_config
                SET value = '0', updated_by = 'migration-033-rollback'
                WHERE key = %s AND value = %s
                """,
                (key, safe_value),
            )
