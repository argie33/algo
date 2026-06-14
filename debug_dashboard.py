#!/usr/bin/env python3
"""Debug dashboard rendering errors."""
import sys
import traceback
import logging
import os

# Add paths for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'tools', 'dashboard'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'utils'))

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

try:
    # Set local API URL
    os.environ['DASHBOARD_API_URL'] = 'http://localhost:3001'

    from utilities import set_api_url
    set_api_url('http://localhost:3001')

    # Import fetchers to load real data
    from fetchers import load_all
    from dashboard import render_dashboard

    # Try to import and test panel rendering
    from panels import panel_portfolio, panel_circuit, panel_header_market

    # Mock data with None values to trigger the error
    risk_data_good = {
        'var95': 2.5,
        'cvar95': 3.2,
        'beta': 1.1,
        'conc5': 45.0,
        'svar': 4.2
    }

    risk_data_none = {
        'var95': None,
        'cvar95': None,
        'beta': None,
        'conc5': None,
        'svar': None
    }

    print("Testing panel_portfolio rendering with good data...")
    try:
        result = panel_portfolio(None, None, risk=risk_data_good)
        print("[OK] panel_portfolio works with good data")
    except Exception as e:
        print(f"[FAIL] panel_portfolio failed with good data: {e}")
        traceback.print_exc()

    print("\nTesting panel_portfolio rendering with None values...")
    try:
        result = panel_portfolio(None, None, risk=risk_data_none)
        print("[OK] panel_portfolio works with None values")
    except Exception as e:
        print(f"[FAIL] panel_portfolio failed with None values: {e}")
        traceback.print_exc()

    print("\nTesting panel_circuit rendering...")
    try:
        cb_data = {
            'any': False,
            'n': 0,
            'bs': [
                {'lbl': 'Test', 'fired': False, 'thr': 100.0, 'cur': 50.0, 'u': '%'},
            ]
        }
        result = panel_circuit(cb_data)
        print("[OK] panel_circuit works")
    except Exception as e:
        print(f"[FAIL] panel_circuit failed: {e}")
        traceback.print_exc()

    print("\n[OK] All tests complete.")

    print("\n\nAttempting to load all data and render dashboard...")
    try:
        print("Loading data from localhost:3001...")
        data = load_all()
        print(f"[OK] Data loaded, keys: {list(data.keys())[:5]}...")

        print("Rendering dashboard...")
        layout = render_dashboard(data, compact=False, elapsed=0.5, frame=0, data_source="LOCAL")
        print("[OK] Dashboard rendered successfully")
    except Exception as e:
        print(f"[FAIL] Dashboard rendering failed: {e}")
        traceback.print_exc()

except Exception as e:
    print(f"Fatal error: {e}")
    traceback.print_exc()
    sys.exit(1)
