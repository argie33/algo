#!/usr/bin/env python3
"""
Check MFI values in the technical_data_daily table
"""

import os
import json
import boto3
import psycopg2
from psycopg2.extras import RealDictCursor
import pandas as pd

def get_db_config():
    """Get database configuration from AWS Secrets Manager"""
    secret_str = boto3.client("secretsmanager") \
                     .get_secret_value(SecretId=os.environ["DB_SECRET_ARN"])["SecretString"]
    sec = json.loads(secret_str)
    return {
        "host":   sec["host"],
        "port":   int(sec.get("port", 5432)),
        "user":   sec["username"],
        "password": sec["password"],
        "dbname": sec["dbname"]
    }

def main():
    try:
        print("🔍 Connecting to database using AWS Secrets Manager...")
        
        # Connect to database
        cfg = get_db_config()
        conn = psycopg2.connect(
            host=cfg["host"], port=cfg["port"],
            user=cfg["user"], password=cfg["password"],
            dbname=cfg["dbname"]
        )
        cur = conn.cursor(cursor_factory=RealDictCursor)
        
        print("✅ Connected successfully!")
        
        # Check if technical_data_daily table exists
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'technical_data_daily'
            ) as table_exists
        """)
        result = cur.fetchone()
        table_exists = result['table_exists']
        
        if not table_exists:
            print("❌ technical_data_daily table does not exist")
            return
        
        print("✅ technical_data_daily table exists")
        
        # Check total rows
        cur.execute("SELECT COUNT(*) as total_rows FROM technical_data_daily")
        result = cur.fetchone()
        total_rows = result['total_rows']
        print(f"📊 Total rows in technical_data_daily: {total_rows}")
        
        if total_rows == 0:
            print("❌ No data in technical_data_daily table")
            return
        
        # Check MFI values specifically
        print("\n🔍 Analyzing MFI values...")
        
        cur.execute("""
            SELECT 
                COUNT(*) as total_records,
                COUNT(mfi) as non_null_mfi,
                COUNT(*) - COUNT(mfi) as null_mfi,
                AVG(mfi) as avg_mfi,
                MIN(mfi) as min_mfi,
                MAX(mfi) as max_mfi,
                COUNT(CASE WHEN mfi > 0 AND mfi < 100 THEN 1 END) as valid_mfi_range
            FROM technical_data_daily
        """)
        result = cur.fetchone()
        
        print(f"📊 MFI Analysis:")
        print(f"   Total records: {result['total_records']}")
        print(f"   Non-null MFI: {result['non_null_mfi']}")
        print(f"   Null MFI: {result['null_mfi']}")
        print(f"   Average MFI: {result['avg_mfi']:.2f}" if result['avg_mfi'] else "   Average MFI: N/A")
        print(f"   Min MFI: {result['min_mfi']}" if result['min_mfi'] else "   Min MFI: N/A")
        print(f"   Max MFI: {result['max_mfi']}" if result['max_mfi'] else "   Max MFI: N/A")
        print(f"   Valid MFI range (0-100): {result['valid_mfi_range']}")
        
        # Check specific symbols for MFI values
        print("\n🔍 Checking MFI for specific symbols...")
        
        cur.execute("""
            SELECT symbol, date, mfi, volume, close
            FROM technical_data_daily 
            WHERE symbol IN ('AAPL', 'MSFT', 'GOOGL', 'TSLA', 'NVDA')
            AND mfi IS NOT NULL
            ORDER BY symbol, date DESC
            LIMIT 20
        """)
        results = cur.fetchall()
        
        if results:
            print("✅ Found MFI values for major stocks:")
            for row in results:
                print(f"   {row['symbol']} | {row['date']} | MFI: {row['mfi']:.2f} | Volume: {row['volume']} | Close: {row['close']}")
        else:
            print("❌ No MFI values found for major stocks")
        
        # Check volume data quality
        print("\n🔍 Checking volume data quality...")
        
        cur.execute("""
            SELECT 
                COUNT(*) as total_records,
                COUNT(volume) as non_null_volume,
                COUNT(CASE WHEN volume > 0 THEN 1 END) as positive_volume,
                COUNT(CASE WHEN volume = 0 THEN 1 END) as zero_volume,
                AVG(volume) as avg_volume,
                MAX(volume) as max_volume
            FROM technical_data_daily
        """)
        result = cur.fetchone()
        
        print(f"📊 Volume Analysis:")
        print(f"   Total records: {result['total_records']}")
        print(f"   Non-null volume: {result['non_null_volume']}")
        print(f"   Positive volume: {result['positive_volume']}")
        print(f"   Zero volume: {result['zero_volume']}")
        print(f"   Average volume: {result['avg_volume']:.0f}" if result['avg_volume'] else "   Average volume: N/A")
        print(f"   Max volume: {result['max_volume']}" if result['max_volume'] else "   Max volume: N/A")
        
        # Check recent MFI calculations
        print("\n🔍 Checking most recent MFI calculations...")
        
        cur.execute("""
            SELECT symbol, date, mfi, volume, close, high, low
            FROM technical_data_daily 
            WHERE date >= CURRENT_DATE - INTERVAL '7 days'
            AND mfi IS NOT NULL
            ORDER BY date DESC, symbol
            LIMIT 10
        """)
        results = cur.fetchall()
        
        if results:
            print("✅ Recent MFI calculations found:")
            for row in results:
                print(f"   {row['symbol']} | {row['date']} | MFI: {row['mfi']:.2f} | Vol: {row['volume']} | OHLC: {row['high']}/{row['low']}/{row['close']}")
        else:
            print("❌ No recent MFI calculations found")
            
            # If no recent MFI, check if there are any recent records at all
            cur.execute("""
                SELECT symbol, date, mfi, volume
                FROM technical_data_daily 
                WHERE date >= CURRENT_DATE - INTERVAL '7 days'
                ORDER BY date DESC, symbol
                LIMIT 10
            """)
            recent_results = cur.fetchall()
            
            if recent_results:
                print("⚠️  Recent records exist but MFI is NULL:")
                for row in recent_results:
                    mfi_status = "NULL" if row['mfi'] is None else f"{row['mfi']:.2f}"
                    vol_status = "NULL" if row['volume'] is None else str(row['volume'])
                    print(f"   {row['symbol']} | {row['date']} | MFI: {mfi_status} | Volume: {vol_status}")
            else:
                print("❌ No recent records found at all")
        
        cur.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
