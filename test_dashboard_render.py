#!/usr/bin/env python3
"""Test dashboard rendering with real data from API."""
import os
import sys
import socket

# Fix Windows encoding
if sys.platform.startswith('win'):
    import io
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except Exception:
        pass

# Auto-detect local
def _is_dev_server_available():
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.5)
        result = sock.connect_ex(('localhost', 3001))
        sock.close()
        return result == 0
    except Exception:
        return False

if _is_dev_server_available():
    os.environ['DASHBOARD_API_URL'] = 'http://localhost:3001'
    os.environ['LOCAL_MODE'] = 'true'

# Load real dashboard data
from dashboard.fetchers import load_all

print("[LOADING] Dashboard data...")
data = load_all()

# Test rendering health panel (most critical)
from dashboard.panels.health import _build_freshness_panel
from dashboard.fetchers_common import FETCHER_METADATA

print("[RENDER] Health panel...")
try:
    health_data = data.get('health', {})

    if health_data.get('_error'):
        print(f"[ERROR] Health data has error: {health_data['_error']}")
    else:
        hlth_items = health_data.get('items', [])
        ready = health_data.get('ready_to_trade')

        print(f"  Items: {len(hlth_items)}")
        print(f"  Ready: {ready}")

        # Try to render
        panel = _build_freshness_panel(hlth_items, ready)
        print(f"  [OK] Panel rendered: {type(panel).__name__}")
except Exception as e:
    print(f"  [ERROR] Rendering failed: {type(e).__name__}: {str(e)[:100]}")

# Test other critical panels
print()
print("[RENDER] Portfolio panel...")
try:
    from dashboard.panels.portfolio import panel_portfolio
    port_data = data.get('port', {})
    panel = panel_portfolio(port_data)
    print(f"  [OK] Rendered: {type(panel).__name__}")
except Exception as e:
    print(f"  [ERROR] {type(e).__name__}: {str(e)[:80]}")

print()
print("[RENDER] Positions panel...")
try:
    from dashboard.panels.positions import panel_positions
    pos_data = data.get('pos', {})
    trades_data = data.get('trades', {})
    panel = panel_positions(pos_data, trades=trades_data)
    print(f"  [OK] Rendered: {type(panel).__name__}")
except Exception as e:
    print(f"  [ERROR] {type(e).__name__}: {str(e)[:80]}")

print()
print("[RENDER] Signals panel...")
try:
    from dashboard.panels.signals import panel_signals
    sig_data = data.get('sig', {})
    scores_data = data.get('scores', {})
    panel = panel_signals(sig_data, scores=scores_data)
    print(f"  [OK] Rendered: {type(panel).__name__}")
except Exception as e:
    print(f"  [ERROR] {type(e).__name__}: {str(e)[:80]}")

print()
print("[SUMMARY] Dashboard rendering test complete")
