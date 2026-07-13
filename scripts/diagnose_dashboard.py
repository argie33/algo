#!/usr/bin/env python3
"""Diagnostic script to identify why dashboard shows 'data not available'."""

import os
import socket
import sys

# Fix Windows console encoding
if sys.platform.startswith('win'):
    import io
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except Exception:
        pass

def check_dev_server() -> tuple[bool, str]:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex(('127.0.0.1', 3001))
        sock.close()
        if result == 0:
            return True, "Dev server is running on localhost:3001"
        else:
            return False, "Dev server NOT running (connection refused on port 3001)"
    except Exception as e:
        return False, f"Error checking dev_server: {e}"

def check_database() -> tuple[bool, str]:
    try:
        import psycopg2
        conn = psycopg2.connect(
            'dbname=stocks user=stocks host=localhost password=stockspassword',
            connect_timeout=5
        )
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM price_daily")
        count = cur.fetchone()[0]
        cur.close()
        conn.close()
        return True, f"Database connected ({count:,} price records)"
    except Exception as e:
        return False, f"Database error: {e}"

def check_api_endpoints() -> tuple[bool, str]:
    try:
        import requests
        headers = {"Authorization": "Bearer dev-admin"}

        response = requests.get(
            "http://localhost:3001/api/algo/portfolio",
            headers=headers,
            timeout=5
        )

        if response.status_code == 200:
            return True, "API responding with data (200 OK)"
        else:
            return False, f"API returned {response.status_code}: {response.text[:100]}"
    except Exception as e:
        return False, f"API error: {e}"

def check_dashboard_import() -> tuple[bool, str]:
    try:
        # Make sure we're running from repo root
        import sys
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if repo_root not in sys.path:
            sys.path.insert(0, repo_root)

        from dashboard.fetchers import load_all  # noqa: F401
        return True, "Dashboard module can be imported"
    except Exception as e:
        return False, f"Cannot import dashboard: {type(e).__name__}: {str(e)[:60]}"

def check_local_mode() -> tuple[bool, str]:
    local_mode = os.environ.get('LOCAL_MODE')
    if local_mode:
        return True, f"LOCAL_MODE is set: {local_mode}"
    else:
        return False, "LOCAL_MODE not set (dashboard will try to use AWS Lambda)"

def main() -> int:
    """Run all diagnostics."""
    print("\n" + "="*80)
    print("ALGO DASHBOARD DIAGNOSTIC")
    print("="*80 + "\n")

    diagnostics = [
        ("LOCAL_MODE env var", check_local_mode),
        ("Dev Server", check_dev_server),
        ("Database", check_database),
        ("API Endpoints", check_api_endpoints),
        ("Dashboard Module", check_dashboard_import),
    ]

    passed = 0
    failed = 0

    for name, check_fn in diagnostics:
        try:
            success, message = check_fn()
            status = "[OK]" if success else "[!]"
            print(f"{status} {name}: {message}")
            if success:
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"[!] {name}: Exception: {e}")
            failed += 1

    print("\n" + "="*80)
    print(f"SUMMARY: {passed} passed, {failed} failed")
    print("="*80 + "\n")

    # Provide recommendations
    if failed == 0:
        print("[OK] All systems operational! Dashboard should work with:\n")
        print("  Terminal 1: python3 api-pkg/dev_server.py")
        print("  Terminal 2: python3 -m dashboard --local\n")
        return 0
    else:
        print("[!] Issues found. Recommended fixes:\n")
        if not os.environ.get('LOCAL_MODE'):
            print("  1. Make sure to use --local flag when starting dashboard:")
            print("     python3 -m dashboard --local\n")

        success, _ = check_dev_server()
        if not success:
            print("  2. Start dev_server first in a separate terminal:")
            print("     python3 api-pkg/dev_server.py")
            print("     (Wait for 'Starting API dev server' message)\n")

        success, _ = check_database()
        if not success:
            print("  3. Check database is running:")
            print("     - PostgreSQL must be running")
            print("     - DB name: 'stocks', user: 'stocks'\n")

        return 1

if __name__ == "__main__":
    sys.exit(main())
