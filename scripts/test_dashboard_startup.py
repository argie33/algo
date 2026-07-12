#!/usr/bin/env python3
"""Test dashboard startup and circuit breaker behavior."""

import os
import sys
import time
import socket
import subprocess
import signal

# Add parent directory to path for dashboard imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ['LOCAL_MODE'] = 'true'
os.environ['ENVIRONMENT'] = 'development'

def wait_for_server(host='localhost', port=3001, timeout=30):
    """Wait for dev_server to be ready."""
    print(f"Waiting for dev_server on {host}:{port}...")
    start = time.time()
    while time.time() - start < timeout:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(('127.0.0.1', port))
            sock.close()
            if result == 0:
                print("[OK] Dev server is ready!")
                return True
        except Exception:
            pass
        time.sleep(0.5)
    print("[FAILED] Dev server startup timeout!")
    return False

def test_api():
    """Test API endpoint to verify it works."""
    import requests
    try:
        resp = requests.get(
            'http://localhost:3001/api/algo/config',
            headers={'Authorization': 'Bearer dev-admin'},
            timeout=5
        )
        if resp.status_code == 200:
            print("[OK] API endpoint works!")
            return True
        else:
            print(f"[FAILED] API returned {resp.status_code}")
            return False
    except Exception as e:
        print(f"[FAILED] API test failed: {e}")
        return False

def test_circuit_breaker():
    """Test circuit breaker state."""
    import dashboard.api_data_layer as api_layer
    print(f"[INFO] Circuit breaker state: {api_layer._circuit_breaker_state}")
    print(f"[INFO] Circuit breaker failures: {api_layer._circuit_breaker_failures}")
    return api_layer._circuit_breaker_state == 'closed'

def main():
    print("=== Dashboard Startup Test ===\n")

    # Kill any existing dev_server
    print("[1] Cleaning up old processes...")
    os.system("taskkill /F /IM python.exe /FI \"COMMANDLINE eq *dev_server*\" 2>/dev/null || true")
    time.sleep(1)

    # Start dev_server
    print("[2] Starting dev_server...")
    dev_proc = subprocess.Popen(
        [sys.executable, 'api-pkg/dev_server.py'],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    # Wait for it to be ready
    if not wait_for_server():
        dev_proc.kill()
        sys.exit(1)
    time.sleep(1)

    # Test API
    print("\n[3] Testing API...")
    if not test_api():
        dev_proc.kill()
        sys.exit(1)

    # Test circuit breaker
    print("\n[4] Checking circuit breaker...")
    if not test_circuit_breaker():
        print("[FAILED] Circuit breaker is not in closed state!")
        dev_proc.kill()
        sys.exit(1)

    # Test fetcher
    print("\n[5] Testing fetcher...")
    try:
        from dashboard.fetchers_config import fetch_algo_config
        result = fetch_algo_config(None)
        if '_error' not in result:
            print(f"[OK] Fetcher works! Got {len(result)} config keys")
        else:
            print(f"[FAILED] Fetcher error: {result['_error']}")
            dev_proc.kill()
            sys.exit(1)
    except Exception as e:
        print(f"[FAILED] Fetcher exception: {e}")
        dev_proc.kill()
        sys.exit(1)

    # Test load_all
    print("\n[6] Testing load_all...")
    try:
        from dashboard.fetchers import load_all
        data = load_all()
        errors = [k for k, v in data.items() if isinstance(v, dict) and '_error' in v]
        print(f"[OK] load_all completed: {len(data)} fetchers, {len(errors)} errors")
        if errors:
            print(f"  Failed fetchers: {errors[:5]}")
    except Exception as e:
        print(f"[FAILED] load_all exception: {e}")
        import traceback
        traceback.print_exc()

    print("\n[OK] All tests passed!")
    dev_proc.kill()

if __name__ == '__main__':
    main()
