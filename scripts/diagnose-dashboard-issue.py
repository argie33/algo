#!/usr/bin/env python3
"""
Diagnose why dashboard shows "data not available".

Checks:
1. Is dev_server running on port 3001?
2. Is the API responding to requests?
3. Is there data in the database?
4. What specific errors is the API returning?
"""

import sys
import json
import subprocess
import time
from typing import Any
from urllib.parse import urljoin

# Add repo root to path
sys.path.insert(0, '/'.join(sys.argv[0].split('/')[:-2]))

def check_port_listening(port: int) -> bool:
    """Check if port is listening."""
    try:
        result = subprocess.run(
            ['netstat', '-tlnp'] if sys.platform != 'win32' else ['netstat', '-ano'],
            capture_output=True,
            text=True,
            timeout=2
        )
        return f':{port}' in result.stdout or f' {port} ' in result.stdout
    except:
        return False


def test_api_endpoint(url: str) -> dict[str, Any]:
    """Test if API endpoint is responding and what it returns."""
    import urllib.request
    import urllib.error

    try:
        req = urllib.request.Request(url)
        req.add_header('Authorization', 'Bearer dev-admin')
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            return {
                'status': response.status,
                'ok': True,
                'data': data
            }
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode()
            data = json.loads(body)
        except:
            data = body
        return {
            'status': e.code,
            'ok': False,
            'error': str(e),
            'data': data
        }
    except Exception as e:
        return {
            'status': None,
            'ok': False,
            'error': str(e),
            'data': None
        }


def check_database_data() -> dict[str, Any]:
    """Check if data exists in the local database."""
    try:
        from utils.db.context import DatabaseContext

        results = {}
        with DatabaseContext('read') as cur:
            # Check critical tables for data
            tables = {
                'market_exposure_daily': 'SELECT COUNT(*) FROM market_exposure_daily',
                'market_health_daily': 'SELECT COUNT(*) FROM market_health_daily',
                'price_daily': 'SELECT COUNT(*) FROM price_daily',
                'algo_positions': 'SELECT COUNT(*) FROM algo_positions WHERE status = \'open\'',
                'algo_trades': 'SELECT COUNT(*) FROM algo_trades',
                'algo_signals': 'SELECT COUNT(*) FROM algo_signals WHERE signal_active = true',
            }

            for table, query in tables.items():
                try:
                    cur.execute(query)
                    count = cur.fetchone()[0]
                    results[table] = count
                except Exception as e:
                    results[table] = f"ERROR: {str(e)[:50]}"

        return results
    except Exception as e:
        return {'error': f"Cannot connect to database: {str(e)[:100]}"}


def main():
    print("=" * 70)
    print("DASHBOARD DIAGNOSIS")
    print("=" * 70)
    print()

    # 1. Check if dev_server is running
    print("[1] Checking if dev_server is running on port 3001...")
    if check_port_listening(3001):
        print("✅ Port 3001 is listening")
    else:
        print("❌ Port 3001 is NOT listening")
        print("   → dev_server is not running!")
        print("   → Start it with: cd api-pkg && python dev_server.py")

    # 2. Try to reach the API
    print()
    print("[2] Testing API health endpoint...")
    health_result = test_api_endpoint('http://localhost:3001/api/health')
    if health_result['ok']:
        print(f"✅ API is responding (status {health_result['status']})")
        print(f"   Health status: {health_result['data'].get('status', 'unknown')}")
    else:
        print(f"❌ API is not responding properly")
        print(f"   Error: {health_result['error']}")

    # 3. Test markets endpoint (what dashboard calls)
    print()
    print("[3] Testing /api/algo/markets endpoint (dashboard data)...")
    markets_result = test_api_endpoint('http://localhost:3001/api/algo/markets')
    if markets_result['ok']:
        print(f"✅ Markets endpoint responding (status {markets_result['status']})")
    else:
        print(f"❌ Markets endpoint returning error")
        print(f"   Status: {markets_result['status']}")
        if isinstance(markets_result['data'], dict):
            print(f"   Error code: {markets_result['data'].get('error', 'unknown')}")
            print(f"   Message: {markets_result['data'].get('message', 'unknown')}")
        else:
            print(f"   Response: {markets_result['data']}")

    # 4. Check database data
    print()
    print("[4] Checking data in database...")
    db_data = check_database_data()
    if 'error' in db_data:
        print(f"❌ Cannot connect to database: {db_data['error']}")
    else:
        all_empty = True
        for table, count in db_data.items():
            if isinstance(count, int):
                status = "✅" if count > 0 else "❌"
                print(f"   {status} {table}: {count} rows")
                if count > 0:
                    all_empty = False
            else:
                print(f"   ⚠️ {table}: {count}")

        if all_empty:
            print()
            print("⚠️  DATABASE IS EMPTY - No data loaded!")
            print("   This is why dashboard shows 'data not available'")
            print("   Fix: Run data loaders or orchestrator to populate data")

    # 5. Summary
    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)

    if not check_port_listening(3001):
        print()
        print("🔴 PRIMARY ISSUE: dev_server is not running")
        print()
        print("Fix:")
        print("  cd api-pkg")
        print("  python dev_server.py")
        print()
        print("Then open dashboard at: http://localhost:5173")
    elif not markets_result['ok']:
        print()
        print("🟡 dev_server is running but API is returning errors")
        print()
        if 'data_unavailable' in str(markets_result.get('data', {})):
            print("This could mean:")
            print("  1. Data hasn't been loaded into the database yet")
            print("  2. The data loaders haven't run")
            print("  3. Database is empty")
            print()
            print("Fix:")
            print("  1. Check database tables (output above)")
            print("  2. Run data loaders: python3 scripts/test_orchestrator_execution.py")
            print("  3. Or trigger orchestrator: python3 scripts/trigger_orchestrator.py")
    else:
        print()
        print("✅ Everything appears to be working!")
        print()
        print("If dashboard still shows 'data not available':")
        print("  1. Hard refresh browser (Ctrl+Shift+R)")
        print("  2. Check browser console for errors")
        print("  3. Verify VITE_PROXY_TARGET is empty or 'http://localhost:3001'")


if __name__ == '__main__':
    main()
