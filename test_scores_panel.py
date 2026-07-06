#!/usr/bin/env python3
"""Test just the scores fetcher and panel."""


print("=" * 80)
print("TEST: Scores Fetcher and Panel")
print("=" * 80)

# Step 1: Fetch scores directly
print("\n1. Fetching scores...")
from dashboard.fetchers_signals import fetch_scores

scores_result = fetch_scores(None)

print(f"   Result type: {type(scores_result)}")
print(f"   Keys: {list(scores_result.keys())}")

if "_error" in scores_result:
    print(f"   ERROR: {scores_result['_error']}")
    exit(1)

if "top" not in scores_result:
    print("   ERROR: 'top' field missing!")
    exit(1)

top = scores_result["top"]
print(f"   Top scores count: {len(top)}")

# Step 2: Check first score
if top:
    first = top[0]
    print("\n2. Checking first score...")
    print(f"   Keys: {list(first.keys())}")

    if "growth_score" in first:
        gs = first["growth_score"]
        print(f"   growth_score: {gs} (type: {type(gs).__name__})")
    else:
        print("   ERROR: growth_score missing from first score!")

# Step 3: Render panel with mock data
print("\n3. Rendering panel with mock data...")
mock_data = {
    "scores": scores_result
}

from dashboard.panels.scores import render_scores

try:
    panel = render_scores(mock_data)
    if panel:
        print("   SUCCESS: Panel rendered!")
        print(f"   Panel type: {type(panel).__name__}")

        # Try to get string representation
        try:
            from rich.console import Console
            console = Console()
            console.print(panel)
        except Exception as e:
            print(f"   (Could not render to console: {e})")
    else:
        print("   ERROR: Panel returned None")
except Exception as e:
    print(f"   ERROR: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
