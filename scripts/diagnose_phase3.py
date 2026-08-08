#!/usr/bin/env python3
"""Diagnose Phase 3 to see why exits aren't being recommended."""

import sys
import logging
from datetime import date as _date, timedelta

# Setup logging
logging.basicConfig(level=logging.DEBUG, format='%(name)s: %(message)s')

from algo.infrastructure.config import AlgoConfig
from algo.monitoring import PositionMonitor
from utils.db import DatabaseContext

config = AlgoConfig()
monitor = PositionMonitor(config)

# Use yesterday's date (Phase 3 in orchestration uses run_date - 1 day)
monitoring_date = _date.today() - timedelta(days=1)
print(f"\n{'='*70}")
print(f"PHASE 3 DIAGNOSTIC - Monitoring date: {monitoring_date}")
print(f"{'='*70}\n")

try:
    recommendations = monitor.review_positions(monitoring_date, cur=None)

    print(f"\nTotal recommendations: {len(recommendations)}")
    print(f"\nBreakdown by action:")
    action_counts = {}
    for rec in recommendations:
        action = rec.get('action', 'UNKNOWN')
        action_counts[action] = action_counts.get(action, 0) + 1

    for action, count in sorted(action_counts.items()):
        print(f"  {action:20s}: {count}")

    print(f"\n{'='*70}")
    print("RECOMMENDATIONS:")
    print(f"{'='*70}\n")

    for rec in recommendations:
        symbol = rec.get('symbol', 'UNKNOWN')
        action = rec.get('action', 'UNKNOWN')
        reason = rec.get('action_reason', '')
        flags = rec.get('flags', [])
        print(f"{symbol:8s} {action:20s} | {reason}")
        if flags:
            print(f"         FLAGS: {', '.join(flags)}")
        print()

except Exception as e:
    import traceback
    print(f"\nERROR: {type(e).__name__}: {e}")
    traceback.print_exc()
    sys.exit(1)
