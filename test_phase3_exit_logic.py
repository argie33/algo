#!/usr/bin/env python3
"""Direct test of Phase 3 exit logic to diagnose why exits aren't being generated."""

import sys
from datetime import datetime, date
from pathlib import Path
from zoneinfo import ZoneInfo

# Setup path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Load environment
from utils.dotenv_loader import load_env_local
load_env_local()

# Load credentials
try:
    from scripts.load_credentials import ensure_credentials_loaded
    ensure_credentials_loaded()
except Exception as e:
    print(f"Warning: Could not load credentials: {e}")

import logging
logging.basicConfig(level=logging.DEBUG)

from algo.infrastructure.config import get_config
from algo.monitoring import PositionMonitor
from utils.db import DatabaseContext

# Get config
config = get_config()

# Create monitor
monitor = PositionMonitor(config)

# Test with today's date
et = ZoneInfo("America/New_York")
test_date = datetime.now(et).date()

print(f"\n{'='*70}")
print(f"DIRECT PHASE 3 TEST - {test_date}")
print(f"{'='*70}")

print(f"\nTesting PositionMonitor.review_positions() with date={test_date}")
try:
    recommendations = monitor.review_positions(current_date=test_date, cur=None)

    print(f"\n{'='*70}")
    print(f"RESULTS: {len(recommendations)} recommendations generated")
    print(f"{'='*70}")

    early_exits = [r for r in recommendations if r["action"] == "EARLY_EXIT"]
    raises = [r for r in recommendations if r["action"] == "RAISE_STOP"]
    holds = [r for r in recommendations if r["action"] == "HOLD"]

    print(f"\nAction breakdown:")
    print(f"  EARLY_EXIT: {len(early_exits)}")
    print(f"  RAISE_STOP: {len(raises)}")
    print(f"  HOLD: {len(holds)}")

    print(f"\nEARLY_EXIT positions:")
    for rec in early_exits:
        print(f"  {rec['symbol']:5s}: {rec.get('action_reason', 'no reason')}")

    print(f"\nRaise_STOP positions:")
    for rec in raises[:3]:
        print(f"  {rec['symbol']:5s}: {rec.get('action_reason', 'no reason')}")
    if len(raises) > 3:
        print(f"  ... and {len(raises) - 3} more")

    # Check database for verification
    print(f"\n{'='*70}")
    print(f"DATABASE STATE VERIFICATION")
    print(f"{'='*70}")
    with DatabaseContext("read") as cur:
        cur.execute("SELECT COUNT(*) FROM algo_positions WHERE status = 'open'")
        open_count = cur.fetchone()[0]

        cur.execute("""
            SELECT symbol, days_since_entry, entry_date, current_price, unrealized_pnl_pct
            FROM algo_positions WHERE status = 'open'
            ORDER BY id LIMIT 3
        """)
        positions = cur.fetchall()

        print(f"\nOpen positions in database: {open_count}")
        print(f"Sample positions:")
        for symbol, days, entry_date, price, pnl_pct in positions:
            print(f"  {symbol:5s}: entry={entry_date}, days={days}, price=\${price:7.2f}, pnl={pnl_pct:6.1f}%")

except Exception as e:
    import traceback
    print(f"\nERROR: {type(e).__name__}: {e}")
    traceback.print_exc()

print(f"\n{'='*70}")
print("Test complete")
print(f"{'='*70}\n")
