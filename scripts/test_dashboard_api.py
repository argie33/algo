#!/usr/bin/env python3
"""Test what dashboard API returns for positions."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import logging

logging.basicConfig(level=logging.DEBUG, format='%(name)s: %(message)s')

import psycopg2.extras

from utils.db.context import DatabaseContext

# Add lambda to path
sys.path.insert(0, str(Path(__file__).parent.parent / "lambda" / "api"))
from routes.algo_handlers.dashboard import _get_algo_positions

print("\n" + "="*80)
print("TESTING DASHBOARD API POSITIONS ENDPOINT")
print("="*80)

with DatabaseContext() as db:
    cur = db.connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    try:
        # Call the actual API handler
        response = _get_algo_positions(cur)

        # Extract response data
        if isinstance(response, tuple):
            status_code = response[0]
            response_data = response[1]
        else:
            status_code = 200
            response_data = response

        print(f"\nHTTP Status: {status_code}")
        print(f"Response type: {type(response_data)}")
        print("\nResponse structure:")
        print(f"  Keys: {list(response_data.keys()) if isinstance(response_data, dict) else 'N/A'}")
        print(f"  Full response: {response_data}")

        if isinstance(response_data, dict):
            # Count items
            items = response_data.get('items', [])
            print(f"\nPositions returned: {len(items)}")

            if items:
                print("\nFirst 5 positions:")
                for i, pos in enumerate(items[:5]):
                    print(f"  [{i+1}] {pos.get('symbol'):6} | "
                          f"qty={pos.get('quantity'):8} | "
                          f"sector={pos.get('sector'):20} | "
                          f"value=${pos.get('position_value'):12}")

            # Coverage
            coverage = response_data.get('coverage', {})
            print("\nCoverage metrics:")
            print(f"  valid_count: {coverage.get('valid_count')}")
            print(f"  total_count: {coverage.get('total_count')}")
            print(f"  filtered_count: {coverage.get('filtered_count')}")
            print(f"  coverage_pct: {coverage.get('coverage_pct')}%")

            # Sector allocation
            sectors = response_data.get('sector_allocation', [])
            print(f"\nSector allocation ({len(sectors)} sectors):")
            for sector in sectors:
                print(f"  {sector['sector']:20} {sector['allocation_pct']:6.1f}%")

            # Alerts
            alerts = response_data.get('stale_alerts', [])
            if alerts:
                print(f"\nAlerts ({len(alerts)}):")
                for alert in alerts:
                    print(f"  - {alert}")

        print("\n" + "="*80)

    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
