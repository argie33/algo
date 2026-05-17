#!/usr/bin/env python3

"""
Pyramid - Add to Winners (Livermore principle)

Per Reminiscences of a Stock Operator + Brian Shannon's Multiple Timeframes
research: the highest-expectancy way to scale capital in a swing trade is to
add to positions that have proven themselves with profit + technical
confirmation, NOT to average down losers.

ENTRY ADDS (each strict gate must pass):
  Add 1 (50% of original size):
      Position is in profit by >= +1R AND
      Initial stop has moved to breakeven AND
      Stock made new closing high in last 5 days AND
      Volume on that breakout > 1.2x 50d-avg
  Add 2 (25% of original size):
      Position is in profit by >= +2R AND
      Stock broke a NEW pivot (20-day high) AND
      Volume confirmed (> 1.5x avg)
  Total adds capped at 3 (Turtle rule).

RISK MANAGEMENT (critical):
  - Combined open risk on the symbol must NEVER exceed original 1R.
  - Each add brings stop tighter (chandelier ratchet on whole position).
  - Adding to a position counts against max_positions slot? NO — same name,
    same slot. But it does count against total_open_risk circuit breaker.

Persists adds to algo_trade_adds table for audit + dashboard display.

Designed to be called from orchestrator phase 4 (after exits, before entries)
so add-decisions don't conflict with new-entry decisions.
"""

from config.credential_helper import get_db_config
from config.env_loader import load_env
from config.credential_helper import get_db_password, get_db_config

try:
    from config.credential_manager import get_credential_manager
    credential_manager = get_credential_manager()
except ImportError:
    credential_manager = None

import os
from utils.db_connection import get_db_connection
from pathlib import Path
from datetime import datetime, date as _date
from algo.algo_pretrade_checks import PreTradeChecks
import logging

logger = logging.getLogger(__name__)

