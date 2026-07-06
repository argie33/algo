#!/usr/bin/env python3
"""Test the complete flow from API to dashboard display."""


print("=" * 80)
print("TEST: Full Dashboard Flow for Scores")
print("=" * 80)

# Step 1: Fetch all data
print("\n1. Loading all dashboard data...")
from dashboard.fetchers import load_all

all_data = load_all()

if "_error" in all_data:
    print(f"ERROR in load_all: {all_data['_error']}")
    exit(1)

print(f"   Loaded {len(all_data)} endpoint data sets")
print(f"   Keys: {list(all_data.keys())}")

# Step 2: Check scores data
print("\n2. Checking 'scores' data...")
if "scores" not in all_data:
    print("   ERROR: 'scores' key missing from loaded data!")
    exit(1)

scores_data = all_data["scores"]
print(f"   Type: {type(scores_data)}")
print(f"   Keys: {list(scores_data.keys())}")

if "_error" in scores_data:
    print(f"   ERROR: {scores_data['_error']}")
    exit(1)

# Step 3: Check top scores
print("\n3. Checking 'top' scores array...")
if "top" not in scores_data:
    print(f"   ERROR: 'top' field missing from scores! Keys: {list(scores_data.keys())}")
    exit(1)

top = scores_data["top"]
print(f"   Type: {type(top)}")
print(f"   Count: {len(top) if isinstance(top, list) else 'N/A'}")

if isinstance(top, list) and top:
    first = top[0]
    print("\n4. Checking first score item...")
    print(f"   Type: {type(first)}")
    print(f"   Keys: {list(first.keys())}")

    if "growth_score" in first:
        gs = first["growth_score"]
        print("   growth_score exists: True")
        print(f"   growth_score value: {gs}")
        print(f"   growth_score type: {type(gs)}")
        print(f"   growth_score is None: {gs is None}")
    else:
        print("   ERROR: growth_score not in first score!")
        exit(1)

    # Step 5: Try rendering
    print("\n5. Attempting to render scores panel...")
    from dashboard.panels.scores import render_scores

    try:
        panel = render_scores(all_data)
        if panel:
            print("   Panel rendered successfully!")
            print(f"   Panel type: {type(panel).__name__}")
            print(f"   Panel title: {panel.title if hasattr(panel, 'title') else 'N/A'}")
        else:
            print("   Panel returned None (no rendering)")
    except Exception as e:
        print(f"   ERROR rendering panel: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
