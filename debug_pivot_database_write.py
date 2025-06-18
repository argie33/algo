#!/usr/bin/env python3
"""
PIVOT DATABASE WRITE DIAGNOSTIC TOOL
This script will trace exactly what happens to pivot values from calculation to database insertion.
"""

import sys
import logging
import json
import os
import psycopg2
from psycopg2.extras import RealDictCursor
import boto3
import numpy as np
import pandas as pd
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - [%(funcName)s:%(lineno)d] - %(message)s",
    stream=sys.stdout
)

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

def sanitize_value(x):
    """EXACT COPY of sanitize function from main script"""
    if x is None:
        return None
    
    # Handle numpy scalar types (float32, float64, int32, etc.)
    if hasattr(x, 'item'):
        x = x.item()  # Convert numpy scalar to Python native type
    
    # Handle NaN/inf values for float types
    if isinstance(x, (float, np.floating)) and (np.isnan(x) or np.isinf(x)):
        return None
    
    # Convert numpy types to native Python types
    if isinstance(x, np.integer):
        return int(x)
    elif isinstance(x, np.floating):
        return float(x)
    elif isinstance(x, np.bool_):
        return bool(x)
    return x

def pivot_high_debug(df, left_bars=3, right_bars=3, shunt=1):
    """EXACT COPY of pivot_high function with enhanced debugging"""
    logging.info(f"🔍 PIVOT HIGH DEBUG: Starting with {len(df)} rows, left={left_bars}, right={right_bars}, shunt={shunt}")
    
    if 'high' not in df.columns:
        logging.error(f"❌ PIVOT ERROR: 'high' column missing from DataFrame. Available columns: {list(df.columns)}")
        return pd.Series(np.full(len(df), np.nan), index=df.index)
    
    # CRITICAL: FORCE SORT DATA BY DATE
    if not df.index.is_monotonic_increasing:
        logging.warning(f"⚠️  PIVOT WARNING: Data not sorted, forcing sort by date index for pivot calculations")
        df = df.sort_index()
    
    pivot_vals = [np.nan] * len(df)
    pivot_count = 0
    
    logging.info(f"🔍 PIVOT HIGH: Scanning {len(df)} bars for pivot highs...")
    
    # Find raw pivots
    for i in range(left_bars, len(df) - right_bars):
        try:
            current_high = df['high'].iloc[i]
            current_date = df.index[i]
            
            if pd.isna(current_high) or current_high <= 0:
                continue
            
            # Check left bars
            left_higher = True
            for j in range(i - left_bars, i):
                left_val = df['high'].iloc[j]
                if pd.isna(left_val) or current_high <= left_val:
                    left_higher = False
                    break
            
            if not left_higher:
                continue
                
            # Check right bars
            right_higher = True
            for j in range(i + 1, i + right_bars + 1):
                right_val = df['high'].iloc[j]
                if pd.isna(right_val) or current_high <= right_val:
                    right_higher = False
                    break
                    
            if left_higher and right_higher:
                confirmed_bar = i + right_bars
                shunted_index = confirmed_bar - shunt
                if 0 <= shunted_index < len(pivot_vals):
                    pivot_vals[shunted_index] = current_high
                    pivot_count += 1
                    shunted_date = df.index[shunted_index]
                    logging.info(f"✅ PIVOT HIGH FOUND: {current_high:.4f} at bar {i} (date: {current_date}) -> stored at bar {shunted_index} (date: {shunted_date})")
        except Exception as e:
            logging.error(f"❌ PIVOT ERROR at index {i}: {str(e)}")
            continue
    
    logging.info(f"🎯 PIVOT HIGH COMPLETE: Found {pivot_count} pivot highs")
    return pd.Series(pivot_vals, index=df.index)

def test_single_symbol_pivot_to_db(symbol="AAPL"):
    """Test complete flow for a single symbol from price data to database insertion"""
    
    logging.info(f"🚀 TESTING COMPLETE PIVOT FLOW FOR SYMBOL: {symbol}")
    logging.info("=" * 80)
    
    # Connect to database
    cfg = get_db_config()
    conn = psycopg2.connect(**cfg)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    
    try:
        # Step 1: Get price data
        logging.info(f"📊 Step 1: Loading price data for {symbol}...")
        cur.execute("""
            SELECT symbol, date, open, high, low, close, volume
            FROM price_daily
            WHERE symbol = %s
            AND volume > 100
            AND close > 0.01
            ORDER BY date ASC
            LIMIT 100
        """, (symbol,))
        
        rows = cur.fetchall()
        if not rows:
            logging.error(f"❌ No price data found for {symbol}")
            return
        
        logging.info(f"✅ Loaded {len(rows)} price records for {symbol}")
        
        # Step 2: Convert to DataFrame
        logging.info(f"📊 Step 2: Converting to DataFrame...")
        df = pd.DataFrame(rows)
        df['date'] = pd.to_datetime(df['date'])
        df.set_index('date', inplace=True)
        df = df.sort_index()  # Ensure sorted
        
        logging.info(f"✅ DataFrame created with {len(df)} rows from {df.index.min()} to {df.index.max()}")
        logging.info(f"📋 High values range: {df['high'].min():.4f} to {df['high'].max():.4f}")
        
        # Step 3: Calculate pivot highs with full debugging
        logging.info(f"📊 Step 3: Calculating pivot highs...")
        pivot_high_series = pivot_high_debug(df, left_bars=3, right_bars=3, shunt=1)
        
        # Step 4: Analyze pivot results
        logging.info(f"📊 Step 4: Analyzing pivot results...")
        pivot_values = pivot_high_series.dropna()
        logging.info(f"🎯 Pivot analysis:")
        logging.info(f"   - Total bars: {len(df)}")
        logging.info(f"   - Pivot highs found: {len(pivot_values)}")
        
        if len(pivot_values) > 0:
            logging.info(f"   - Pivot values: {pivot_values.tolist()}")
            logging.info(f"   - Pivot dates: {pivot_values.index.tolist()}")
            
            # Step 5: Test sanitization
            logging.info(f"📊 Step 5: Testing value sanitization...")
            for date, value in pivot_values.items():
                sanitized = sanitize_value(value)
                logging.info(f"   - Original: {value} ({type(value)}) -> Sanitized: {sanitized} ({type(sanitized)})")
        else:
            logging.warning(f"⚠️  No pivot highs found - checking if this is expected...")
            
        # Step 6: Prepare database insertion data
        logging.info(f"📊 Step 6: Preparing database insertion...")
        
        # Create a single test record with pivot data
        test_date = df.index[-10] if len(df) >= 10 else df.index[-1]  # Use a recent date
        test_pivot_value = pivot_high_series.loc[test_date] if test_date in pivot_high_series.index else None
        
        logging.info(f"🧪 Test record preparation:")
        logging.info(f"   - Test date: {test_date}")
        logging.info(f"   - Raw pivot value: {test_pivot_value}")
        logging.info(f"   - Sanitized pivot value: {sanitize_value(test_pivot_value)}")
        
        # Step 7: Insert test record
        logging.info(f"📊 Step 7: Inserting test record to database...")
        
        insert_sql = """
        INSERT INTO technical_data_daily (
            symbol, date, pivot_high, fetched_at
        ) VALUES (%s, %s, %s, NOW())
        ON CONFLICT (symbol, date) DO UPDATE SET
            pivot_high = EXCLUDED.pivot_high,
            fetched_at = EXCLUDED.fetched_at
        """
        
        cur.execute(insert_sql, (
            symbol,
            test_date,
            sanitize_value(test_pivot_value)
        ))
        conn.commit()
        
        logging.info(f"✅ Test record inserted/updated successfully")
        
        # Step 8: Verify database write
        logging.info(f"📊 Step 8: Verifying database write...")
        
        cur.execute("""
            SELECT symbol, date, pivot_high, fetched_at
            FROM technical_data_daily
            WHERE symbol = %s AND date = %s
        """, (symbol, test_date))
        
        result = cur.fetchone()
        if result:
            logging.info(f"✅ Database verification successful:")
            logging.info(f"   - Symbol: {result['symbol']}")
            logging.info(f"   - Date: {result['date']}")
            logging.info(f"   - Pivot High: {result['pivot_high']}")
            logging.info(f"   - Fetched At: {result['fetched_at']}")
            
            if result['pivot_high'] is not None:
                logging.info(f"🎉 SUCCESS: Pivot value successfully written to database!")
            else:
                logging.warning(f"⚠️  Pivot value is NULL in database")
        else:
            logging.error(f"❌ No record found in database after insertion")
        
        # Step 9: Check all pivot values for this symbol
        logging.info(f"📊 Step 9: Checking all pivot values for {symbol}...")
        
        cur.execute("""
            SELECT COUNT(*) as total_records,
                   COUNT(pivot_high) as non_null_pivots,
                   MIN(pivot_high) as min_pivot,
                   MAX(pivot_high) as max_pivot
            FROM technical_data_daily
            WHERE symbol = %s
        """, (symbol,))
        
        stats = cur.fetchone()
        if stats:
            logging.info(f"📊 Database pivot statistics for {symbol}:")
            logging.info(f"   - Total records: {stats['total_records']}")
            logging.info(f"   - Non-null pivots: {stats['non_null_pivots']}")
            logging.info(f"   - Min pivot: {stats['min_pivot']}")
            logging.info(f"   - Max pivot: {stats['max_pivot']}")
            
    except Exception as e:
        logging.error(f"❌ Error during testing: {str(e)}")
        import traceback
        logging.error(f"❌ Full traceback: {''.join(traceback.format_exc())}")
    finally:
        cur.close()
        conn.close()

def main():
    """Main diagnostic function"""
    logging.info("🔍 PIVOT DATABASE WRITE DIAGNOSTIC TOOL")
    logging.info("=" * 80)
    
    # Test with a known liquid stock
    test_single_symbol_pivot_to_db("AAPL")
    
    logging.info("=" * 80)
    logging.info("🏁 Diagnostic complete")

if __name__ == "__main__":
    main()
