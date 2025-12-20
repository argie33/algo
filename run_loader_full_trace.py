#!/usr/bin/env python3
import os
import sys
import psycopg2
from datetime import date

sys.path.insert(0, '/home/stocks/algo')

# Monkey-patch the logger to get full errors
import loadcoveredcallopportunities as loader_module
original_calculate = loader_module.calculate_opportunities

def wrapped_calculate(conn, data_date):
    try:
        return original_calculate(conn, data_date)
    except Exception as e:
        import traceback
        print("=" * 60)
        print("FULL TRACEBACK:")
        traceback.print_exc()
        print("=" * 60)
        raise

loader_module.calculate_opportunities = wrapped_calculate

from loadcoveredcallopportunities import get_db_config, ensure_covered_calls_table

try:
    db_config = get_db_config()
    conn = psycopg2.connect(**db_config)
    
    with conn.cursor() as cur:
        ensure_covered_calls_table(cur, conn)
    
    # Get most recent date
    with conn.cursor() as cur:
        cur.execute("SELECT MAX(data_date) FROM options_chains WHERE option_type = 'call';")
        recent_date = cur.fetchone()[0]
    
    print(f"Running with data_date: {recent_date}")
    count = loader_module.calculate_opportunities(conn, recent_date)
    print(f"✅ Success: {count} opportunities loaded")
    
    conn.close()
    
except Exception as e:
    print(f"Error occurred")
