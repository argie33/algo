#!/usr/bin/env python3
"""Monitor GitHub Actions deployment progress."""

import os
import psycopg2
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime

env_file = Path('.env.local')
if env_file.exists():
    load_dotenv(env_file)

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "user": os.getenv("DB_USER", "stocks"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "stocks"),
}

print("=" * 80)
print("WORKFLOW DEPLOYMENT MONITOR")
print("Time: {}".format(datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
print("=" * 80)
print()

# Check database
try:
    conn = psycopg2.connect(**DB_CONFIG)
    cur = conn.cursor()
    
    print("DATABASE STATUS:")
    print("-" * 80)
    
    # Check critical tables
    tables = [
        'stock_symbols', 'price_daily', 'buy_sell_daily',
        'market_overview', 'annual_balance_sheet', 'swing_trader_scores'
    ]
    
    for table in tables:
        try:
            cur.execute("SELECT COUNT(*) FROM {}".format(table))
            count = cur.fetchone()[0]
            print("  [OK] {}: {:,} rows".format(table, count))
        except:
            print("  [FAIL] {}: table missing or error".format(table))
            conn.rollback()
    
    cur.close()
    conn.close()
    
    print()
    print("DATABASE CONNECTION: SUCCESS")
    
except Exception as e:
    print("DATABASE CONNECTION: FAILED")
    print("Error: {}".format(str(e)[:100]))

print()
print("=" * 80)
print("GITHUB ACTIONS STATUS:")
print("-" * 80)
print()
print("Expected Timeline:")
print("  Phase 1: detect-changes         - identify modified loaders")
print("  Phase 2: deploy-infrastructure  - deploy CloudFormation (ECS, RDS)")
print("  Phase 3: build-loaders          - build Docker images (parallel, max 5)")
print("  Phase 4: register-task-defs     - register ECS task definitions")
print("  Phase 5: READY                  - loaders can execute")
print()
print("Timeline: 30-45 minutes total")
print()
print("Monitor at: https://github.com/argie33/algo/actions")
print()
print("=" * 80)
print("Ready to check logs and deployment status.")
print("=" * 80)

