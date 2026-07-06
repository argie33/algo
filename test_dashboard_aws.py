import sys

sys.path.insert(0, '.')

import os

from dashboard.api_data_layer import api_call

# Set API URL for AWS
os.environ['DASHBOARD_API_URL'] = 'https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com'

print("Testing dashboard API data layer...")
print(f"API URL: {os.environ['DASHBOARD_API_URL']}")
print("")

try:
    # Test fetching run status (should not show "data_unavailable")
    print("[1] Fetching last-run status...")
    data = api_call("/api/algo/last-run")

    if isinstance(data, dict):
        if data.get('data_unavailable'):
            print(f"  FAIL: Got data_unavailable: {data.get('reason')}")
        else:
            print("  SUCCESS: Got run data")
            run_id = data.get('data', {}).get('run_id', 'N/A')
            success = data.get('data', {}).get('success', False)
            print(f"    Run ID: {run_id}")
            print(f"    Success: {success}")
except Exception as e:
    print(f"  ERROR: {e}")

print("")
try:
    # Test fetching portfolio
    print("[2] Fetching portfolio...")
    data = api_call("/api/algo/portfolio")

    if isinstance(data, dict):
        if data.get('data_unavailable'):
            print(f"  FAIL: Got data_unavailable: {data.get('reason')}")
        else:
            print("  SUCCESS: Got portfolio data")
            value = data.get('data', {}).get('total_portfolio_value', 'N/A')
            cash = data.get('data', {}).get('total_cash', 'N/A')
            positions = data.get('data', {}).get('position_count', 0)
            print(f"    Portfolio Value: ${value}")
            print(f"    Cash: ${cash}")
            print(f"    Positions: {positions}")
except Exception as e:
    print(f"  ERROR: {e}")

print("")
print("✓ Dashboard can successfully fetch AWS data!")
