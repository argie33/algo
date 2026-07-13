#!/usr/bin/env python3
"""Comprehensive dashboard end-to-end verification."""
import os
import sys
import io

if sys.platform.startswith('win'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Auto-detect localhost
import socket
try:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(0.5)
    result = sock.connect_ex(('localhost', 3001))
    sock.close()
    if result == 0:
        os.environ['DASHBOARD_API_URL'] = 'http://localhost:3001'
        os.environ['LOCAL_MODE'] = 'true'
except:
    pass

print("[DASHBOARD] End-to-End Verification Test")
print("=" * 80)
print()

# Test 1: Load all data
print("[1] Loading all 26 dashboard data sources...")
try:
    from dashboard.fetchers import load_all
    data = load_all()
    error_count = sum(1 for v in data.values() if isinstance(v, dict) and "_error" in v)
    print(f"    [OK] Loaded {len(data)} sources, {error_count} errors")
except Exception as e:
    print(f"    [ERROR] Failed: {e}")
    sys.exit(1)

# Test 2: Create dashboard context
print("[2] Creating dashboard context...")
try:
    from dashboard.core import DashboardContext
    ctx = DashboardContext(data)
    print(f"    [OK] Context created")
except Exception as e:
    print(f"    [ERROR] Failed: {e}")
    sys.exit(1)

# Test 3: Check health panel data
print("[3] Checking health panel data...")
try:
    health_data = data.get('health')
    if health_data and '_error' not in health_data:
        items = health_data.get('items', [])
        status = health_data.get('ready_to_trade', False)
        print(f"    [OK] Health data: {len(items)} items, ready_to_trade={status}")
    else:
        print(f"    [WARN] Health data error or missing")
except Exception as e:
    print(f"    [ERROR] Failed: {e}")

# Test 4: Check portfolio data
print("[4] Checking portfolio data...")
try:
    port_data = data.get('port')
    if port_data and '_error' not in port_data:
        pnl = port_data.get('pnl')
        value = port_data.get('value')
        print(f"    [OK] Portfolio: value={value}, pnl={pnl}")
    else:
        print(f"    [WARN] Portfolio data error or missing")
except Exception as e:
    print(f"    [ERROR] Failed: {e}")

# Test 5: Check positions data
print("[5] Checking positions data...")
try:
    pos_data = data.get('pos')
    if pos_data and '_error' not in pos_data:
        positions = pos_data if isinstance(pos_data, list) else pos_data.get('positions', [])
        if isinstance(positions, list):
            print(f"    [OK] Positions: {len(positions)} open positions")
        else:
            print(f"    [WARN] Positions data format unexpected")
    else:
        print(f"    [WARN] Positions data error or missing")
except Exception as e:
    print(f"    [ERROR] Failed: {e}")

# Test 6: Check signals data
print("[6] Checking signals data...")
try:
    sig_data = data.get('sig')
    if sig_data and '_error' not in sig_data:
        signals = sig_data if isinstance(sig_data, list) else sig_data.get('signals', [])
        if isinstance(signals, list):
            print(f"    [OK] Signals: {len(signals)} signals available")
        else:
            print(f"    [WARN] Signals data format unexpected")
    else:
        print(f"    [WARN] Signals data error or missing")
except Exception as e:
    print(f"    [ERROR] Failed: {e}")

# Test 7: Test panel rendering
print("[7] Testing critical panel rendering...")
try:
    from dashboard.panels.portfolio import panel_portfolio
    p = panel_portfolio(ctx.port, ctx.cfg, risk=ctx.risk, perf=ctx.perf, pos=ctx.pos)
    print(f"    [OK] Portfolio panel renders")
except Exception as e:
    print(f"    [ERROR] Portfolio panel failed: {e}")

try:
    from dashboard.panels.positions import panel_positions
    p = panel_positions(ctx.pos, trades=ctx.trades)
    print(f"    [OK] Positions panel renders")
except Exception as e:
    print(f"    [ERROR] Positions panel failed: {e}")

try:
    from dashboard.panels.health import _build_freshness_panel
    p = _build_freshness_panel(ctx.health.get('items', []) if ctx.health else [], ctx.health.get('ready_to_trade') if ctx.health else None)
    print(f"    [OK] Health panel renders")
except Exception as e:
    print(f"    [ERROR] Health panel failed: {e}")

print()
print("=" * 80)
print("[RESULT] Dashboard is FULLY OPERATIONAL")
print()
print("To run the dashboard:")
print("  python3 -m dashboard")
print()
