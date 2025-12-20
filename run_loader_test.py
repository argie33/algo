#!/usr/bin/env python3
import os
import sys
import psycopg2
from datetime import date, timedelta

# Temporarily modify the loader to use the most recent data_date
sys.path.insert(0, '/home/stocks/algo')
from loadcoveredcallopportunities import get_db_config, ensure_covered_calls_table, calculate_opportunities

try:
    db_config = get_db_config()
    conn = psycopg2.connect(**db_config)
    
    # Ensure table exists
    with conn.cursor() as cur:
        ensure_covered_calls_table(cur, conn)
    
    # Get most recent date
    with conn.cursor() as cur:
        cur.execute("SELECT MAX(data_date) FROM options_chains WHERE option_type = 'call';")
        result = cur.fetchone()
        if result and result[0]:
            recent_date = result[0]
        else:
            recent_date = date.today()
    
    print(f"Running loader with data_date: {recent_date}")
    
    # Calculate opportunities
    count = calculate_opportunities(conn, recent_date)
    
    conn.close()
    print(f"✅ Successfully loaded {count} opportunities")
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
