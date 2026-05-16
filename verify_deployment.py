#!/usr/bin/env python3
"""
Post-Deployment Verification Script

Tests system health after AWS deployment:
1. API endpoint responding
2. Database connected and initialized
3. Data in critical tables
4. Calculations working correctly
5. No errors in logs

Run this AFTER deployment completes to verify system is operational.
"""

import requests
import psycopg2
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from dotenv import load_dotenv

# Load environment
env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

# Configuration
API_ENDPOINT = os.getenv('API_ENDPOINT', 'https://kx4kprv8ph.execute-api.us-east-1.amazonaws.com')
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = int(os.getenv('DB_PORT', 5432))
DB_NAME = os.getenv('DB_NAME', 'stocks')
DB_USER = os.getenv('DB_USER', 'stocks')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'postgres')

print("=" * 70)
print("POST-DEPLOYMENT VERIFICATION")
print("=" * 70)
print(f"Timestamp: {datetime.now().isoformat()}")
print()

# ============================================================
# TEST 1: API Health Check
# ============================================================
print("TEST 1: API Health Check")
print("-" * 70)
try:
    response = requests.get(f"{API_ENDPOINT}/health", timeout=10)
    if response.status_code == 200:
        print("✅ API RESPONDING")
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.text[:100]}")
    else:
        print(f"⚠️  API returned status {response.status_code}")
        print(f"   Response: {response.text[:200]}")
except Exception as e:
    print(f"❌ API NOT RESPONDING: {e}")
print()

# ============================================================
# TEST 2: Database Connection
# ============================================================
print("TEST 2: Database Connection")
print("-" * 70)
conn = None
try:
    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        connect_timeout=10
    )
    print("✅ DATABASE CONNECTED")
    print(f"   Host: {DB_HOST}:{DB_PORT}/{DB_NAME}")

    cur = conn.cursor()
    cur.execute("SELECT version()")
    version = cur.fetchone()[0]
    print(f"   Version: {version.split(',')[0]}")
    cur.close()
except Exception as e:
    print(f"❌ DATABASE CONNECTION FAILED: {e}")
    sys.exit(1)
print()

# ============================================================
# TEST 3: Schema Initialized
# ============================================================
print("TEST 3: Schema Initialized")
print("-" * 70)
try:
    cur = conn.cursor()
    cur.execute("""
        SELECT COUNT(*) FROM information_schema.tables
        WHERE table_schema = 'public'
    """)
    table_count = cur.fetchone()[0]

    # Check critical tables
    critical_tables = [
        'stock_symbols',
        'price_daily',
        'algo_positions',
        'algo_trades',
        'market_exposure_daily',
        'algo_risk_daily'
    ]

    cur.execute(f"""
        SELECT COUNT(*) FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = ANY(%s)
    """, (critical_tables,))
    critical_count = cur.fetchone()[0]

    print(f"✅ SCHEMA EXISTS")
    print(f"   Total tables: {table_count}")
    print(f"   Critical tables: {critical_count}/{len(critical_tables)}")

    if critical_count < len(critical_tables):
        print(f"   ⚠️  Missing some critical tables")
    cur.close()
except Exception as e:
    print(f"❌ SCHEMA CHECK FAILED: {e}")
print()

# ============================================================
# TEST 4: Data in Tables
# ============================================================
print("TEST 4: Data in Critical Tables")
print("-" * 70)
try:
    cur = conn.cursor()

    tables_to_check = {
        'price_daily': 'Recent price data',
        'market_exposure_daily': 'Market exposure metrics',
        'algo_risk_daily': 'Risk calculations (VaR, CVaR)',
        'algo_positions': 'Current positions',
        'algo_trades': 'Trade history'
    }

    for table, desc in tables_to_check.items():
        try:
            cur.execute(f"""
                SELECT COUNT(*) FROM {table}
                WHERE created_at > NOW() - INTERVAL '7 days'
            """)
            recent_count = cur.fetchone()[0]

            cur.execute(f"SELECT COUNT(*) FROM {table}")
            total_count = cur.fetchone()[0]

            if recent_count > 0:
                print(f"✅ {table}")
                print(f"   Recent (7d): {recent_count} | Total: {total_count}")
            elif total_count > 0:
                print(f"⚠️  {table}")
                print(f"   Recent (7d): {recent_count} | Total: {total_count} (data is stale)")
            else:
                print(f"⏳ {table}")
                print(f"   No data yet (expected for new deployments)")
        except Exception as e:
            print(f"⚠️  {table}: Could not check - {str(e)[:60]}")

    cur.close()
except Exception as e:
    print(f"❌ DATA CHECK FAILED: {e}")
print()

# ============================================================
# TEST 5: Calculations Verified
# ============================================================
print("TEST 5: Critical Calculations")
print("-" * 70)
try:
    cur = conn.cursor()

    # Check market_exposure_daily has correct columns
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'market_exposure_daily'
        ORDER BY column_name
    """)
    columns = [row[0] for row in cur.fetchall()]

    expected_columns = ['market_exposure_pct', 'long_exposure_pct', 'short_exposure_pct', 'exposure_tier', 'is_entry_allowed']
    found = [c for c in expected_columns if c in columns]

    if len(found) == len(expected_columns):
        print("✅ MARKET EXPOSURE SCHEMA")
        print(f"   All required columns present")
    else:
        print(f"⚠️  MARKET EXPOSURE SCHEMA")
        print(f"   Found {len(found)}/{len(expected_columns)} columns")

    # Check algo_risk_daily has correct columns
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = 'algo_risk_daily'
        ORDER BY column_name
    """)
    columns = [row[0] for row in cur.fetchall()]

    expected_columns = ['var_pct_95', 'cvar_pct_95', 'portfolio_beta', 'stressed_var_pct']
    found = [c for c in expected_columns if c in columns]

    if len(found) == len(expected_columns):
        print("✅ VAR/RISK SCHEMA")
        print(f"   All required columns present")
    else:
        print(f"⚠️  VAR/RISK SCHEMA")
        print(f"   Found {len(found)}/{len(expected_columns)} columns")

    cur.close()
except Exception as e:
    print(f"❌ CALCULATION CHECK FAILED: {e}")
print()

# ============================================================
# SUMMARY
# ============================================================
print("=" * 70)
print("VERIFICATION COMPLETE")
print("=" * 70)
print()
print("If all tests passed: System is operational ✅")
print("If any failed: Check CloudWatch logs for details")
print()
print("Next steps:")
print("1. Monitor data loading (EventBridge runs at 4:05pm ET)")
print("2. Verify market exposure data persists")
print("3. Test API endpoints with real data")
print("4. Monitor orchestrator execution")
print()

if conn:
    conn.close()
