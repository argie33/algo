#!/usr/bin/env python3
"""
Migration 002: Widen market_exposure_daily.exposure_tier VARCHAR(20) -> VARCHAR(50)

The exposure tier value 'tier_1_strong_uptrend' is 21 chars, exceeding the
VARCHAR(20) limit set by the ADD COLUMN migration. This widens the column to
VARCHAR(50) so all tier values fit without truncation errors.
"""

from migrations.migration_helper import DatabaseContext

DESCRIPTION = "Widen market_exposure_daily.exposure_tier to VARCHAR(50)"


def up():
    with DatabaseContext("write") as cur:
        cur.execute("""
            ALTER TABLE market_exposure_daily
                ALTER COLUMN exposure_tier TYPE VARCHAR(50)
        """)


def down():
    with DatabaseContext("write") as cur:
        cur.execute("""
            ALTER TABLE market_exposure_daily
                ALTER COLUMN exposure_tier TYPE VARCHAR(20)
        """)
