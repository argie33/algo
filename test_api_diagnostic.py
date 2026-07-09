#!/usr/bin/env python3
"""Diagnostic script to test API positions endpoint logic."""
import json
import sys
from decimal import Decimal
from datetime import datetime, date

sys.path.insert(0, '.')
from utils.db import get_db_connection
from utils.data_queries import get_open_positions
import psycopg2.extras

print("[DIAGNOSTIC] Starting positions endpoint test...")

# Step 1: Connect and fetch positions
print("\n[STEP 1] Fetching positions from database...")
conn = get_db_connection()
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
positions = get_open_positions(cur, limit=1000)
print(f"[OK] Fetched {len(positions)} positions")

# Step 2: Build sector allocation (same logic as API)
print("\n[STEP 2] Building sector allocation...")
sector_allocation = {}
for p in positions:
    sector = p.get("sector")
    if sector is None:
        raise RuntimeError(f"[CRITICAL] Position missing sector: {p.get('symbol')}")
    position_value = p.get("position_value")
    if position_value is None:
        raise RuntimeError(f"[CRITICAL] Position missing value: {p.get('symbol')}")

    val = float(position_value)
    if sector not in sector_allocation:
        sector_allocation[sector] = 0.0
    sector_allocation[sector] += val

total_value = sum(sector_allocation.values())
print(f"[OK] Total portfolio value: ${total_value:.2f}")

if total_value <= 0:
    print("[WARNING] Portfolio has $0 value")
    sector_list = []
else:
    sector_list = [
        {
            "sector": s,
            "allocation_pct": round((v / total_value) * 100, 1),
            "is_overweight": (v / total_value) * 100 > 30,
        }
        for s, v in sorted(sector_allocation.items(), key=lambda x: x[1], reverse=True)
    ]
    print(f"[OK] Built {len(sector_list)} sector allocations")

# Step 3: Build response (same as API)
print("\n[STEP 3] Building response object...")
response = {
    "statusCode": 200,
    "data": {
        "items": positions,
        "sector_allocation": sector_list,
        "pagination": {"total": len(positions), "limit": 10000, "offset": 0},
        "coverage": {
            "valid_count": len(positions),
            "total_count": len(positions),
            "filtered_count": 0,
            "coverage_pct": 100.0,
        },
        "stale_alerts": [],
        "data_freshness": {
            "data_age_days": 0,
            "is_stale": False,
            "max_date": "2026-07-05",
            "warning": None,
        },
    },
}
print("[OK] Response object built")

# Step 4: JSON encode (same as _send_json)
print("\n[STEP 4] JSON encoding with default encoder...")

def json_encoder(obj):
    """Handle non-standard types."""
    # Handle datetime before date since datetime is a subclass of date
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    if obj is None:
        return None
    # If all else fails, try converting to string as fallback
    try:
        return str(obj)
    except Exception:
        raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")

try:
    json_str = json.dumps(response, default=json_encoder)
    print(f"[OK] Successfully encoded to JSON ({len(json_str)} bytes)")

    # Print first 300 chars
    print(f"\n[PREVIEW] First 300 chars:\n{json_str[:300]}...")

    # Parse back to verify
    parsed = json.loads(json_str)
    print(f"\n[OK] Successfully parsed JSON back")
    print(f"[OK] Response contains {len(parsed['data']['items'])} positions")

except Exception as e:
    print(f"[ERROR] {e}")
    import traceback
    traceback.print_exc()

conn.close()
print("\n[DIAGNOSTIC] Complete")
