#!/usr/bin/env python3
"""
Migration 1144: Add downside volatility metrics to stability_metrics table

Downside volatility measures the standard deviation of only negative returns,
providing a better risk metric than traditional volatility since investors care
more about losses than gains. Adds 30d, 60d, and 252d downside volatility columns
plus unavailability reason tracking.
"""

from utils.db.context import DatabaseContext

DESCRIPTION = "Add downside volatility columns to stability_metrics"


def up():
    with DatabaseContext("write") as cur:
        # Check if columns already exist (idempotent)
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'stability_metrics'
            AND column_name = 'downside_volatility_30d'
        """)
        if cur.fetchone():
            return

        # Add downside volatility columns
        cur.execute("""
            ALTER TABLE stability_metrics
            ADD COLUMN downside_volatility_30d NUMERIC(10, 4) NULL,
            ADD COLUMN downside_volatility_60d NUMERIC(10, 4) NULL,
            ADD COLUMN downside_volatility_252d NUMERIC(10, 4) NULL,
            ADD COLUMN downside_volatility_30d_unavailable_reason VARCHAR(255) NULL,
            ADD COLUMN downside_volatility_60d_unavailable_reason VARCHAR(255) NULL,
            ADD COLUMN downside_volatility_252d_unavailable_reason VARCHAR(255) NULL
        """)


def down():
    """Drop downside volatility columns from stability_metrics."""
    with DatabaseContext("write") as cur:
        cur.execute("""
            ALTER TABLE stability_metrics
            DROP COLUMN IF EXISTS downside_volatility_30d,
            DROP COLUMN IF EXISTS downside_volatility_60d,
            DROP COLUMN IF EXISTS downside_volatility_252d,
            DROP COLUMN IF EXISTS downside_volatility_30d_unavailable_reason,
            DROP COLUMN IF EXISTS downside_volatility_60d_unavailable_reason,
            DROP COLUMN IF EXISTS downside_volatility_252d_unavailable_reason
        """)
