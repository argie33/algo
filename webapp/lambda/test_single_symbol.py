#!/usr/bin/env python3
"""
Quick test of stock score calculation for a single symbol
"""
import os
import sys
sys.path.insert(0, '/home/stocks/algo/webapp/lambda')

os.environ['DB_HOST'] = 'localhost'
os.environ['DB_PORT'] = '5432'
os.environ['DB_NAME'] = 'stocks'
os.environ['DB_USER'] = 'postgres'
os.environ['DB_PASSWORD'] = 'password'

from loadstockscores import get_stock_data_from_database, get_db_connection

try:
    conn = get_db_connection()
    result = get_stock_data_from_database(conn, 'AAPL')
    if result:
        print("✅ AAPL Score Calculation SUCCESS")
        print(f"Composite Score: {result.get('composite_score')}")
        print(f"Sentiment Score: {result.get('sentiment_score')}")
        print(f"Positioning Score: {result.get('positioning_score')}")
    else:
        print("❌ AAPL Score Calculation returned None")
    conn.close()
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
