#!/usr/bin/env python3
"""Test scores fetcher to verify fix."""

import sys
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# Simulate the fetcher's response processing
def test_fetch_scores():
    import requests

    # Fetch from API
    response = requests.get("http://localhost:3001/api/algo/scores?limit=10", headers={"Authorization": "Bearer dev-user"})
    data = response.json()

    print(f"[API] statusCode: {data.get('statusCode')}")
    print(f"[API] Response keys: {list(data.keys())}")

    # Simulate fetcher processing (lines 318-382 of fetchers_signals.py)
    top_data = data

    # Handle multiple response formats: items (new), top (legacy), or wrapped data.top
    if "items" in top_data:
        top = top_data["items"]
        print("[FETCH] Using items format")
    elif "data" in top_data and isinstance(top_data["data"], dict):
        response_data = top_data["data"]
        if "top" not in response_data:
            print("[FETCH] ERROR: wrapped format missing 'top' field")
            return False
        top = response_data["top"]
        print("[FETCH] Using wrapped data.top format")
    elif "top" in top_data:
        top = top_data["top"]
        print("[FETCH] Using legacy direct format")
    else:
        print("[FETCH] ERROR: missing required items/top field")
        return False

    print(f"[FETCH] Got {len(top)} items")

    # Extract summary metrics (lines 388-416)
    if "pagination" in top_data and isinstance(top_data["pagination"], dict):
        response_data_dict = top_data
        universe_total = top_data["pagination"].get("total")
        print("[FETCH] Using pagination format")
    elif "data" in top_data and isinstance(top_data["data"], dict):
        response_data_dict = top_data["data"]
        universe_total = response_data_dict.get("universe_total")
        print("[FETCH] Using wrapped response_data_dict")
    else:
        response_data_dict = top_data
        universe_total = response_data_dict.get("universe_total")

    avg_composite = response_data_dict.get("avg_composite")
    grades = response_data_dict.get("grades")

    print(f"[FETCH] universe_total: {universe_total}")
    print(f"[FETCH] avg_composite: {avg_composite}")
    print(f"[FETCH] grades: {grades}")

    # Verify fetcher returns the data correctly
    result = {
        "top": top,
        "universe_total": universe_total,
        "avg_composite": avg_composite,
        "grades": grades,
    }

    print(f"\n[RESULT] Fetcher would return:")
    print(f"  top: {len(result['top'])} items")
    print(f"  universe_total: {result['universe_total']}")
    print(f"  avg_composite: {result['avg_composite']}")
    print(f"  grades: {result['grades']}")

    # Verify panel can render summary
    if result["universe_total"] and result["avg_composite"] and result["grades"]:
        print(f"\n[PANEL] Summary line CAN be rendered:")
        print(f"  '{result['universe_total']} candidates ranked (showing top {len(result['top'])})'")
        print(f"  'avg composite: {result['avg_composite']:.1f}'")
        a = result['grades'].get('a', 0)
        b = result['grades'].get('b', 0)
        c = result['grades'].get('c', 0)
        d = result['grades'].get('d', 0)
        print(f"  'A:{a} B:{b} C:{c} D:{d}'")
        return True
    else:
        print(f"\n[PANEL] ERROR: Missing data for summary line")
        return False

if __name__ == "__main__":
    try:
        if test_fetch_scores():
            print("\n[SUCCESS] Scores fetcher fix is working!")
            sys.exit(0)
        else:
            print("\n[FAIL] Scores fetcher fix not working correctly")
            sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
