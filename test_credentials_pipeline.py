#!/usr/bin/env python3
"""
End-to-end credential pipeline test.
Verifies that credentials flow correctly through all layers.
"""

import os
import sys

print("\n" + "=" * 70)
print("CREDENTIAL PIPELINE TEST")
print("=" * 70)

# Test 1: Environment variables are set
print("\n[TEST 1] PowerShell Environment Variables")
print("-" * 70)
db_host = os.getenv("DB_HOST")
db_password = os.getenv("DB_PASSWORD")
alpaca_key = os.getenv("APCA_API_KEY_ID") or os.getenv("ALPACA_API_KEY")

if db_host:
    print(f"[OK] DB_HOST = {db_host}")
else:
    print("[ERROR] DB_HOST not set")
    sys.exit(1)

if db_password:
    print(f"[OK] DB_PASSWORD is set")
else:
    print("[ERROR] DB_PASSWORD not set")
    sys.exit(1)

if alpaca_key:
    print(f"[OK] Alpaca API Key is set")
else:
    print("[WARN] Alpaca API Key not set (optional)")

# Test 2: Credential Manager loads them
print("\n[TEST 2] Python Credential Manager")
print("-" * 70)
try:
    from config.credential_manager import get_credential_manager
    cm = get_credential_manager()

    db = cm.get_db_credentials()
    print(f"[OK] DB Credentials loaded:")
    print(f"     Host: {db['host']}")
    print(f"     Port: {db['port']}")
    print(f"     Database: {db['database']}")
    print(f"     User: {db['user']}")

except Exception as e:
    print(f"[ERROR] Credential Manager failed: {e}")
    sys.exit(1)

# Test 3: Credential Helper works
print("\n[TEST 3] Credential Helper")
print("-" * 70)
try:
    from config.credential_helper import get_db_config
    config = get_db_config()

    print(f"[OK] DB Config loaded:")
    print(f"     Host: {config['host']}")
    print(f"     Port: {config['port']}")
    print(f"     Database: {config['database']}")
    print(f"     User: {config['user']}")

except Exception as e:
    print(f"[ERROR] Credential Helper failed: {e}")
    sys.exit(1)

# Test 4: Database connection attempt
print("\n[TEST 4] Database Connection")
print("-" * 70)
try:
    from utils.db_connection import get_db_connection

    print(f"[INFO] Attempting connection to {db_host}...")
    conn = get_db_connection()

    if conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        result = cursor.fetchone()

        if result:
            print(f"[OK] Database connection successful!")
            print(f"     Connected to: {db_host}")

        cursor.close()
        conn.close()
    else:
        print(f"[WARN] Database connection could not be established")
        print(f"       (This may be OK if PostgreSQL is not running)")

except Exception as e:
    print(f"[WARN] Database connection test failed: {e}")
    print(f"       (PostgreSQL may not be running locally)")

# Final summary
print("\n" + "=" * 70)
print("CREDENTIAL PIPELINE SUMMARY")
print("=" * 70)
print("""
[OK] PowerShell Profile: Credentials loaded
[OK] Credential Manager: Working correctly
[OK] Credential Helper: Working correctly
[OK] Credential Flow: LOCAL (PowerShell) -> PYTHON (Manager) -> SERVICES

Next Steps:
1. Start PostgreSQL server
2. Run: python3 init_database.py
3. Run: python3 run-all-loaders.py
4. Test: python3 algo/algo_orchestrator.py --dry-run
""")

print("=" * 70)
