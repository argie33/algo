#!/usr/bin/env python3
"""Test dashboard API endpoints to identify which panels are unavailable."""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

# Mock the API credentials
os.environ["DASHBOARD_API_URL"] = os.environ.get("DASHBOARD_API_URL", "http://localhost:8000")
os.environ["COGNITO_USER_POOL_ID"] = os.environ.get("COGNITO_USER_POOL_ID", "test")
os.environ["COGNITO_CLIENT_ID"] = os.environ.get("COGNITO_CLIENT_ID", "test")

from dashboard.api_data_layer import set_api_url, set_cognito_auth
from dashboard.error_boundary import has_error
from dashboard.fetchers import load_all

print("=" * 80)
print("DASHBOARD PANEL AVAILABILITY TEST")
print("=" * 80)
print()

# Try to fetch all dashboard data
try:
    print("Fetching all dashboard data...")
    data = load_all()

    print("\n" + "=" * 80)
    print("PANEL STATUS REPORT")
    print("=" * 80)
    print()

    panels = {
        "mkt": ("Market Data", data.get("mkt")),
        "cfg": ("Algo Config", data.get("cfg")),
        "exp_factors": ("Exposure Factors", data.get("exp_factors")),
        "health": ("Health/Risk", data.get("health")),
        "run": ("Run Status", data.get("run")),
        "activity": ("Recent Activity", data.get("activity")),
        "perf": ("Performance Analytics", data.get("perf")),
        "eco": ("Economic Data", data.get("eco")),
        "port": ("Portfolio", data.get("port")),
        "pos": ("Positions", data.get("pos")),
        "sig": ("Signals", data.get("sig")),
        "scores": ("Signal Scores", data.get("scores")),
        "risk": ("Risk Metrics", data.get("risk")),
        "srank": ("Sector Ranking", data.get("srank")),
        "cb": ("Circuit Breakers", data.get("cb")),
        "trades": ("Recent Trades", data.get("trades")),
        "econ_cal": ("Economic Calendar", data.get("econ_cal")),
        "sentiment": ("Market Sentiment", data.get("sentiment")),
        "perf_anl": ("Performance Analysis", data.get("perf_anl")),
    }

    available = []
    unavailable = []

    for _panel_key, (panel_name, panel_data) in panels.items():
        if panel_data is None:
            status = "NOT FETCHED"
            unavailable.append((panel_name, status))
        elif has_error(panel_data):
            error_msg = panel_data.get("_error", "Unknown error")
            status = f"ERROR: {error_msg[:70]}"
            unavailable.append((panel_name, status))
        else:
            status = "OK"
            available.append(panel_name)

        # Format output
        status_icon = "[OK]" if status == "OK" else "[UNAVAILABLE]"
        print(f"{status_icon:15} {panel_name:30} {status}")

    print()
    print("=" * 80)
    print(f"SUMMARY: {len(available)} available, {len(unavailable)} unavailable")
    print("=" * 80)
    print()

    if unavailable:
        print("UNAVAILABLE PANELS:")
        for panel_name, status in unavailable:
            print(f"  - {panel_name}: {status}")

    if available:
        print("\nAVAILABLE PANELS:")
        for panel_name in available:
            print(f"  - {panel_name}")

except Exception as e:
    print(f"ERROR: {e}")
    import traceback

    traceback.print_exc()
