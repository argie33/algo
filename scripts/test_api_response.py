#!/usr/bin/env python3
"""Test what the API returns for positions."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import json

import psycopg2.extras

from utils.db.context import DatabaseContext

# Simulate what the API endpoint returns
# Add lambda to path
sys.path.insert(0, str(Path(__file__).parent.parent / "lambda" / "api"))
from routes.algo_handlers.dashboard import _get_algo_positions

with DatabaseContext() as db:
    cur = db.connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    print("\n=== Testing _get_algo_positions() API Endpoint ===\n")

    try:
        response = _get_algo_positions(cur)

        # Parse JSON response
        if hasattr(response, 'json'):
            data = json.loads(response.json())
        else:
            # It's already a dict or tuple from json_response
            data = response[1] if isinstance(response, tuple) else response

        print(f"Response status: {response[0] if isinstance(response, tuple) else 200}")

        if 'items' in data:
            items = data['items']
            print(f"Total items returned: {len(items)}")
            print(f"Items IDs/symbols: {[item.get('symbol') for item in items]}")

            if items:
                print("\nFirst position details:")
                for key in ['symbol', 'quantity', 'position_value', 'sector', 'status']:
                    if key in items[0]:
                        print(f"  {key}: {items[0][key]}")

        if 'coverage' in data:
            coverage = data['coverage']
            print("\nCoverage metrics:")
            print(f"  valid_count: {coverage.get('valid_count')}")
            print(f"  total_count: {coverage.get('total_count')}")
            print(f"  filtered_count: {coverage.get('filtered_count')}")
            print(f"  coverage_pct: {coverage.get('coverage_pct')}")

        if 'sector_allocation' in data:
            sectors = data['sector_allocation']
            print(f"\nSector allocation ({len(sectors)} sectors):")
            for s in sectors[:5]:
                print(f"  {s['sector']:20} {s['allocation_pct']:5.1f}%")

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
