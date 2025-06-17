#!/usr/bin/env python3
"""
Diagnostic script to check database table status
"""
import psycopg2
from psycopg2.extras import RealDictCursor
import boto3
import json
import os

def get_db_config():
    secret_str = boto3.client("secretsmanager") \
                     .get_secret_value(SecretId=os.environ["DB_SECRET_ARN"])["SecretString"]
    sec = json.loads(secret_str)
    return {
        "host": sec["host"],
        "port": int(sec.get("port", 5432)),
        "user": sec["username"],
        "password": sec["password"],
        "dbname": sec["dbname"]
    }

def check_database_status():
    """Check key tables and their row counts"""
    try:
        cfg = get_db_config()
        conn = psycopg2.connect(**cfg)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        # Key tables to check
        key_tables = [
            'price_daily',
            'technical_data_daily', 
            'buy_sell_daily',
            'buy_sell_weekly',
            'buy_sell_monthly',
            'fear_greed_index',
            'aaii_sentiment',
            'stock_symbols'
        ]
        
        print("=== DATABASE TABLE STATUS ===")
        print()
        
        for table in key_tables:
            try:
                # Check if table exists
                cur.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_schema = 'public' 
                        AND table_name = %s
                    )
                """, (table,))
                
                exists = cur.fetchone()['exists']
                
                if exists:
                    # Get row count
                    cur.execute(f"SELECT COUNT(*) as count FROM {table}")
                    count = cur.fetchone()['count']
                    
                    # Get latest date if it has a date column
                    try:
                        cur.execute(f"SELECT MAX(date) as latest_date FROM {table} LIMIT 1")
                        latest = cur.fetchone()['latest_date']
                        print(f"✅ {table}: {count:,} rows (latest: {latest})")
                    except:
                        print(f"✅ {table}: {count:,} rows")
                        
                else:
                    print(f"❌ {table}: TABLE DOES NOT EXIST")
                    
            except Exception as e:
                print(f"❌ {table}: ERROR - {str(e)}")
        
        print()
        print("=== STOCK SYMBOLS CHECK ===")
        try:
            cur.execute("SELECT COUNT(*) as count FROM stock_symbols WHERE exchange IN ('NASDAQ', 'New York Stock Exchange')")
            symbol_count = cur.fetchone()['count']
            print(f"Available stock symbols: {symbol_count:,}")
            
            if symbol_count > 0:
                cur.execute("SELECT symbol FROM stock_symbols WHERE exchange IN ('NASDAQ', 'New York Stock Exchange') LIMIT 5")
                samples = cur.fetchall()
                print(f"Sample symbols: {', '.join([r['symbol'] for r in samples])}")
            else:
                print("⚠️  NO STOCK SYMBOLS FOUND - This is likely the root cause!")
                
        except Exception as e:
            print(f"❌ Error checking stock symbols: {e}")
        
        print()
        print("=== DIAGNOSIS ===")
        
        # Check if core data pipeline is working
        try:
            cur.execute("SELECT COUNT(*) as count FROM price_daily")
            price_count = cur.fetchone()['count']
            
            cur.execute("SELECT COUNT(*) as count FROM technical_data_daily") 
            tech_count = cur.fetchone()['count']
            
            if price_count == 0:
                print("❌ CRITICAL: No price data - run loadpricedaily.py first")
            elif tech_count == 0:
                print("❌ CRITICAL: No technical data - run loadtechnicalsdaily.py")
            else:
                print("✅ Core data pipeline appears to be working")
                
        except Exception as e:
            print(f"❌ Error checking core pipeline: {e}")
            
        cur.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        print("Check if:")
        print("1. Database is running")
        print("2. DB_SECRET_ARN environment variable is set")
        print("3. AWS credentials are configured")

if __name__ == "__main__":
    check_database_status()
