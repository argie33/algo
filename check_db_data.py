#!/usr/bin/env python3
import os
import sys
import json
import boto3
import psycopg2

# Get DB credentials from Secrets Manager
client = boto3.client("secretsmanager", region_name="us-east-1")
try:
    secret = json.loads(client.get_secret_value(SecretId="stocks-db-credentials")["SecretString"])
    
    conn = psycopg2.connect(
        host=secret["host"],
        port=secret.get("port", 5432),
        user=secret["username"],
        password=secret["password"],
        dbname=secret["dbname"]
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
    
    # Check stock_symbols
    cur.execute("SELECT COUNT(*) FROM stock_symbols")
    count = cur.fetchone()[0]
    print(f"stock_symbols: {count} rows")
    
    # Check price_daily
    cur.execute("SELECT COUNT(*) FROM price_daily")
    count = cur.fetchone()[0]
    print(f"price_daily: {count} rows")
    
    # Check technical_data_daily
    cur.execute("SELECT COUNT(*) FROM technical_data_daily")
    count = cur.fetchone()[0]
    print(f"technical_data_daily: {count} rows")
    
    # Check stock_scores
    cur.execute("SELECT COUNT(*) FROM stock_scores")
    count = cur.fetchone()[0]
    print(f"stock_scores: {count} rows")
    
    # Check sector_performance
    cur.execute("SELECT COUNT(*) FROM sector_performance")
    count = cur.fetchone()[0]
    print(f"sector_performance: {count} rows")
    
    cur.close()
    conn.close()
    
except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)
