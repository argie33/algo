#!/usr/bin/env python3
"""Centralized Market Timing Constants

Single source of truth for all market hours and timing values.
Instead of scattered hardcoded time(9, 30) and hour=9/minute=30 across files,
define them once here and import everywhere.

Usage:
    from utils.infrastructure import MARKET_OPEN_HOUR, MARKET_OPEN_MINUTE, MARKET_OPEN_TIME

    market_open_et = now_et.replace(hour=MARKET_OPEN_HOUR, minute=MARKET_OPEN_MINUTE)
    if now.time() >= MARKET_OPEN_TIME:
        # Market is open
"""

from datetime import time

# US equity market timing (Eastern Time)
MARKET_OPEN_HOUR = 9
MARKET_OPEN_MINUTE = 30
MARKET_OPEN_TIME = time(9, 30)

MARKET_CLOSE_HOUR = 16
MARKET_CLOSE_MINUTE = 0
MARKET_CLOSE_TIME = time(16, 0)

# Early close time (half-days: day before Independence Day, day after Thanksgiving, Christmas Eve)
MARKET_EARLY_CLOSE_HOUR = 15
MARKET_EARLY_CLOSE_MINUTE = 0
MARKET_EARLY_CLOSE_TIME = time(15, 0)

# Alternative: 1 PM early close (some half-days)
MARKET_ALT_EARLY_CLOSE_HOUR = 13
MARKET_ALT_EARLY_CLOSE_MINUTE = 0
MARKET_ALT_EARLY_CLOSE_TIME = time(13, 0)

# Orchestrator run schedule (ET)
ORCHESTRATOR_RUN_TIMES = [
    time(9, 30),  # Market open
    time(13, 0),  # 1 PM
    time(15, 0),  # 3 PM
    time(17, 30),  # 5:30 PM (post-market)
]

# Orchestrator as (hour, minute) tuples for backward compatibility
ORCHESTRATOR_RUN_TIMES_TUPLE = [
    (9, 30),  # Market open
    (13, 0),  # 1 PM
    (15, 0),  # 3 PM
    (17, 30),  # 5:30 PM
]

# Time buffer before orchestrator run to assess if subprocess will complete
# Morning window: 2-9:30 AM = 450 min; expected load ~285 min; buffer=15 allows 2:00+240min=6:00
ORCHESTRATOR_KILL_BUFFER_MINUTES = 15
