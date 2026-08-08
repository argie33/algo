#!/usr/bin/env python3
"""Test what the sizer returns when at position limit."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))

from algo.trading.position_sizer import PositionSizer
from algo.infrastructure.config.main import AlgoConfig
import json

# Load config
config = AlgoConfig()
sizer_config = config.to_dict() if hasattr(config, "to_dict") else dict(config)

# Create sizer
sizer = PositionSizer(config=sizer_config)

print("="*80)
print("TESTING SIZER BEHAVIOR")
print("="*80)

# Test 1: Normal case (should work)
print("\nTest 1: Normal case (entry_price=$100, stop=$95)")
result = sizer.calculate_position_size(
    symbol="TEST1",
    entry_price=100.0,
    stop_loss_price=95.0,
    portfolio_value=100000.0,
)
print(f"Result: {json.dumps(result, indent=2, default=str)}")
print(f"Has 'status' key: {'status' in result}")
if 'status' in result:
    print(f"Status value: {result['status']}")

# Test 2: Check what happens at position limit
print("\n" + "="*80)
print("Test 2: At position limit (should return no_room)")
print("="*80)

# First, check how many positions are open
from utils.db.context import DatabaseContext
with DatabaseContext("read") as cur:
    cur.execute("SELECT COUNT(*) FROM algo_positions WHERE status = 'open'")
    open_count = cur.fetchone()[0]

    print(f"Current open positions: {open_count}")

    max_pos = sizer_config.get("max_positions", 15)
    print(f"Max positions from config: {max_pos}")

    if open_count >= max_pos:
        print(f"[WARNING] Already at limit ({open_count}/{max_pos})")
        print("Trying to size a position anyway...")
    else:
        print(f"[INFO] Not at limit yet ({open_count}/{max_pos})")

result = sizer.calculate_position_size(
    symbol="TEST2",
    entry_price=100.0,
    stop_loss_price=95.0,
    portfolio_value=100000.0,
)
print(f"Result: {json.dumps(result, indent=2, default=str)}")
print(f"Has 'status' key: {'status' in result}")
if 'status' in result:
    print(f"Status value: {result['status']}")
    print(f"Shares: {result.get('shares', 'N/A')}")
else:
    print(f"WARNING: No 'status' key in result!")
    print(f"Keys present: {list(result.keys())}")

print("\n" + "="*80)
print("CONCLUSION")
print("="*80)
if 'status' in result and result.get('shares') == 0:
    print(f"When shares=0, status is: '{result['status']}'")
    if result['status'] != "no_room":
        print(f"[PROBLEM] Expected 'no_room' but got '{result['status']}'")
else:
    print("No clear indication of position limit rejection")
