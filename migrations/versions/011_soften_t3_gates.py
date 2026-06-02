#!/usr/bin/env python3
"""
Migration 007: Soften T3 RS-slope and volume-decay hard gates.

Both gates hard-reject consolidating bases — exactly the setups Minervini trading
wants to find. A stock building a tight base will naturally show:
  - Flat or slightly negative RS-line slope over 10 days (consolidating near highs)
  - Declining volume (drying up = institutional accumulation, not distribution)

Setting these to warn-only (gate disabled) lets legitimate breakout setups through
while still logging the data for human review. The other T3 gates (Stage 2, Minervini
score, 52w range, weekly chart) remain hard gates and maintain quality.

Both config keys were seeded as 'true' in migration 005. This migration explicitly
overwrites them to 'false' only if they are still at the default 'true' value.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from utils.database_context import DatabaseContext

DESCRIPTION = "Soften T3 RS-slope and volume-decay gates from hard-reject to warn-only"


def up():
    with DatabaseContext('write') as cur:
        cur.execute(
            """
            UPDATE algo_config
            SET value = 'false', updated_by = 'migration-007'
            WHERE key = 'rs_slope_gate_enabled' AND value = 'true'
            """
        )
        cur.execute(
            """
            UPDATE algo_config
            SET value = 'false', updated_by = 'migration-007'
            WHERE key = 'volume_decay_gate_enabled' AND value = 'true'
            """
        )


def down():
    with DatabaseContext('write') as cur:
        cur.execute(
            """
            UPDATE algo_config
            SET value = 'true', updated_by = 'migration-007-rollback'
            WHERE key IN ('rs_slope_gate_enabled', 'volume_decay_gate_enabled')
              AND value = 'false' AND updated_by = 'migration-007'
            """
        )
