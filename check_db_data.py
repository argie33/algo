#!/usr/bin/env python3
import os
import sys
import json
import psycopg2

# Get DB credentials from environment variables
try:
    conn = psycopg2.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        port=int(os.environ.get("DB_PORT", 5432)),
        user=os.environ.get("DB_USER", "stocks"),
        password=os.environ.get("DB_PASSWORD", "stocks"),
        dbname=os.environ.get("DB_NAME", "stocks")
    )
    
    cur = conn.cursor()
    
    # Check what tables exist
    cur.execute("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'public' 
        ORDER BY table_name
    """)
    tables = [row[0] for row in cur.fetchall()]
    print(f"Tables in database: {len(tables)}")
    print(", ".join(tables[:10]))
    print()
    
    # Check aaii_sentiment
    if "aaii_sentiment" in tables:
        cur.execute("SELECT COUNT(*) FROM aaii_sentiment")
        count = cur.fetchone()[0]
        print(f"aaii_sentiment: {count} rows")
        if count > 0:
            print("Last 5 rows from aaii_sentiment:")
            cur.execute("SELECT * FROM aaii_sentiment ORDER BY date DESC LIMIT 5")
            for row in cur.fetchall():
                print(row)
    else:
        print("aaii_sentiment table not found")

    cur.close()
    conn.close()
    
except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)
