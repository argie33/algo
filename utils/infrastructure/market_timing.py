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

# Upper bound for the orchestrator's top-level market-hours guard on MONITOR_ONLY runs only
# (evening/default/prewarm/manual - see lambda_function.py's MONITOR_ONLY_RUN_IDENTIFIERS).
# The evening orchestrator is intentionally scheduled at 5:30 PM ET, after MARKET_CLOSE_TIME,
# for post-close "final position management" (terraform/modules/services/2x-daily-orchestrator.tf)
# - it never places new entries (Phase 8 has its own is_market_open() guard for that) and is
# hardcoded dry_run=True with no way to override to live. Using MARKET_CLOSE_TIME as the upper
# bound for these runs too meant the evening run hit "outside_market_hours" and skipped entirely,
# every single day it fired at its real scheduled time, in both local dev and production - live
# 2026-08-17 confirmed via orchestrator_execution_log. Does NOT affect LIVE_TRADING_RUN_IDENTIFIERS
# (morning/afternoon/preclose/premarket), which still use MARKET_OPEN_TIME/MARKET_CLOSE_TIME as
# both bounds - this only widens the window for runs that can never place real orders.
MONITOR_WINDOW_CLOSE_TIME = time(18, 0)

# Early close time (half-days: day before Independence Day, day after Thanksgiving, Christmas
# Eve) - NYSE/NASDAQ close these at 1:00 PM ET, not 3:00 PM. There is no separate 3:00 PM
# variant in current practice; a prior version of this file defined one (unused, never
# correct) alongside this constant under an "Alternative" label - removed to avoid two
# candidate early-close times sitting side by side with no indication which one is real.
MARKET_EARLY_CLOSE_HOUR = 13
MARKET_EARLY_CLOSE_MINUTE = 0
MARKET_EARLY_CLOSE_TIME = time(13, 0)

# Orchestrator run schedule (ET) - runs every 5 minutes during market hours
# Dashboard requires portfolio snapshots fresher than 360s, so 5-min frequency ensures data freshness
ORCHESTRATOR_RUN_TIMES = []
for hour in range(9, 17):  # 9 AM to 4 PM (covers 9:30 AM to 4 PM market hours)
    for minute in range(0, 60, 5):
        ORCHESTRATOR_RUN_TIMES.append(time(hour, minute))

# Orchestrator as (hour, minute) tuples for backward compatibility
ORCHESTRATOR_RUN_TIMES_TUPLE = [(h.hour, h.minute) for h in ORCHESTRATOR_RUN_TIMES]

# Time buffer before orchestrator run to assess if subprocess will complete
# Morning window: 2-9:30 AM = 450 min; expected load ~285 min; buffer=15 allows 2:00+240min=6:00
ORCHESTRATOR_KILL_BUFFER_MINUTES = 15
