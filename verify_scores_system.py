#!/usr/bin/env python3
"""Comprehensive scores data system verification script."""

import sys
import os
sys.path.insert(0, os.getcwd())

def check_database():
    """Check if scores are loaded in database."""
    print("\n=== DATABASE CHECK ===")
    try:
        from utils.db import get_db_connection
        conn = get_db_connection()
        cur = conn.cursor()

        # Total scores
        cur.execute("SELECT COUNT(*) FROM stock_scores")
        total = cur.fetchone()[0]

        # Scores with composite_score
        cur.execute("SELECT COUNT(*) FROM stock_scores WHERE composite_score IS NOT NULL")
        with_score = cur.fetchone()[0]

        # Sample
        cur.execute("""
            SELECT symbol, composite_score, quality_score, growth_score, momentum_score
            FROM stock_scores
            WHERE composite_score IS NOT NULL
            LIMIT 3
        """)
        samples = cur.fetchall()

        print(f"[OK] Total scores in database: {total}")
        print(f"[OK] Scores with composite_score: {with_score}")
        print(f"[OK] Sample scores:")
        for sym, comp, qual, grow, mom in samples:
            print(f"   {sym}: composite={comp}, quality={qual}, growth={grow}, momentum={mom}")

        cur.close()
        return True
    except Exception as e:
        print(f"[FAIL] Database error: {e}")
        return False


def check_dev_server():
    """Check if dev_server is running on localhost:3001."""
    print("\n=== DEV SERVER CHECK ===")
    import socket
    import requests

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(("127.0.0.1", 3001))
        sock.close()

        if result != 0:
            print(f"[FAIL] Dev server NOT running on localhost:3001")
            return False

        print(f"[OK] Dev server listening on localhost:3001")

        # Test health endpoint
        try:
            resp = requests.get("http://localhost:3001/api/health", timeout=5)
            if resp.status_code == 200:
                print(f"[OK] Health endpoint responds: {resp.status_code}")
                return True
            else:
                print(f"[FAIL] Health endpoint returned: {resp.status_code}")
                return False
        except requests.exceptions.RequestException as e:
            print(f"[FAIL] Health endpoint error: {e}")
            return False
    except Exception as e:
        print(f"[FAIL] Connection check error: {e}")
        return False


def check_endpoints():
    """Check if API endpoints return data."""
    print("\n=== API ENDPOINTS CHECK ===")
    import requests

    endpoints = [
        ("/api/algo/scores?limit=5", "Python CLI endpoint"),
        ("/api/scores/stockscores?limit=5", "React app endpoint"),
    ]

    all_ok = True
    for path, desc in endpoints:
        try:
            resp = requests.get(f"http://localhost:3001{path}", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                # Count scores
                scores = None
                if "data" in data and "top" in data["data"]:
                    scores = len(data["data"]["top"])
                elif "top" in data:
                    scores = len(data["top"])
                elif "data" in data and "items" in data["data"]:
                    scores = len(data["data"]["items"])
                elif "items" in data:
                    scores = len(data["items"])

                print(f"[OK] {desc}: {resp.status_code} ({scores or 'unknown'} scores)")
            else:
                print(f"[FAIL] {desc}: {resp.status_code}")
                all_ok = False
        except Exception as e:
            print(f"[FAIL] {desc}: {e}")
            all_ok = False

    return all_ok


def check_cli_fetcher():
    """Check if CLI fetch_scores function works."""
    print("\n=== CLI FETCHER CHECK ===")
    try:
        from dashboard.fetchers_signals import fetch_scores
        result = fetch_scores(None)

        if "_error" in result:
            print(f"[FAIL] CLI fetch_scores returned error: {result['_error']}")
            return False

        top_scores = result.get("top", [])
        print(f"[OK] CLI fetch_scores returned: {len(top_scores)} scores")
        if top_scores:
            first = top_scores[0]
            print(f"   First: {first.get('symbol', '?')} = {first.get('composite_score', '?')}")

        return len(top_scores) > 0
    except Exception as e:
        print(f"[FAIL] CLI fetcher error: {e}")
        return False


def check_api_config():
    """Check API configuration."""
    print("\n=== API CONFIGURATION ===")
    from dashboard.api_data_layer import _get_api_base_url_with_source

    api_url, source = _get_api_base_url_with_source()
    print(f"API URL: {api_url}")
    print(f"Source: {source}")

    is_localhost = "localhost" in api_url or "127.0.0.1" in api_url
    if is_localhost:
        print("[OK] Using localhost (good for dev)")
    else:
        print("[WARN]  Using AWS endpoint (check if deployed)")

    return is_localhost


def main():
    print("=" * 60)
    print("SCORES DATA SYSTEM VERIFICATION")
    print("=" * 60)

    results = {
        "Database": check_database(),
        "Dev Server": check_dev_server(),
        "API Endpoints": check_endpoints(),
        "CLI Fetcher": check_cli_fetcher(),
        "API Config": check_api_config(),
    }

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for check, passed in results.items():
        status = "[OK] PASS" if passed else "[FAIL] FAIL"
        print(f"{status}: {check}")

    all_passed = all(results.values())
    if all_passed:
        print("\n[OK] ALL CHECKS PASSED - Scores system is healthy!")
        print("\nIf you're still seeing 'No Data' in the UI:")
        print("1. Check browser DevTools (F12) Network tab for API errors")
        print("2. Check Console tab for JavaScript errors")
        print("3. Verify React app is on localhost:5173+ (not AWS)")
    else:
        print("\n[FAIL] SOME CHECKS FAILED - See details above")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
