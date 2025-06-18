#!/usr/bin/env python3
"""
Debug pivot calculations in production data - Enhanced version

This script will:
1. Connect to the production database
2. Fetch actual price data for a sample stock
3. Test the pivot calculations with detailed debugging
4. Show exactly what's happening with pivot H/L calculations
"""

import sys
import logging
import json
import os
import psycopg2
from psycopg2.extras import RealDictCursor
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Setup logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
    stream=sys.stdout
)

def get_db_config():
    """Get database configuration from environment variables"""
    try:
        return {
            "host": os.getenv('DB_HOST'),
            "port": int(os.getenv('DB_PORT', 5432)),
            "user": os.getenv('DB_USER'),
            "password": os.getenv('DB_PASSWORD'),
            "dbname": os.getenv('DB_NAME')
        }
    except Exception as e:
        logging.error(f"Failed to get DB config: {e}")
        return None

def pivot_high_debug(df, left_bars=3, right_bars=3, shunt=1, symbol=""):
    """
    Debug version of pivot high calculation with extensive logging
    """
    logging.info(f"🔍 PIVOT HIGH DEBUG for {symbol}")
    logging.info(f"📊 Data shape: {df.shape}")
    logging.info(f"📅 Date range: {df.index.min()} to {df.index.max()}")
    logging.info(f"📈 High range: {df['high'].min():.2f} to {df['high'].max():.2f}")
    logging.info(f"⚙️  Parameters: left={left_bars}, right={right_bars}, shunt={shunt}")
    
    # Check data sorting
    is_sorted = df.index.is_monotonic_increasing
    logging.info(f"📋 Data is sorted: {is_sorted}")
    if not is_sorted:
        logging.error("❌ Data is NOT sorted - this will break pivot calculations!")
        # Sort the data
        df = df.sort_index()
        logging.info("✅ Data sorted successfully")
    
    # Show sample data
    logging.info(f"📋 Sample data (first 10 rows):")
    sample_data = df[['high', 'low', 'close']].head(10)
    for idx, row in sample_data.iterrows():
        logging.info(f"   {idx}: H={row['high']:.2f}, L={row['low']:.2f}, C={row['close']:.2f}")
    
    pivot_vals = [np.nan] * len(df)
    pivot_count = 0
    
    # Calculate minimum data needed
    min_data_needed = left_bars + right_bars + 1
    logging.info(f"📊 Minimum data needed: {min_data_needed}, Available: {len(df)}")
    
    if len(df) < min_data_needed:
        logging.error(f"❌ Insufficient data: need {min_data_needed}, have {len(df)}")
        return pd.Series(pivot_vals, index=df.index)
    
    # Check for NaN or invalid values
    nan_count = df['high'].isna().sum()
    zero_negative = (df['high'] <= 0).sum()
    logging.info(f"📊 Data quality: {nan_count} NaN values, {zero_negative} zero/negative values")
    
    # Main pivot calculation with detailed logging
    logging.info(f"🔄 Starting pivot calculation loop...")
    
    for i in range(left_bars, len(df) - right_bars):
        current_high = df['high'].iloc[i]
        current_date = df.index[i]
        
        # Skip invalid values
        if pd.isna(current_high) or current_high <= 0:
            continue
        
        # Check left bars
        left_higher = True
        left_max = 0
        for j in range(i - left_bars, i):
            left_val = df['high'].iloc[j]
            if pd.isna(left_val):
                left_higher = False
                break
            left_max = max(left_max, left_val)
            if current_high <= left_val:
                left_higher = False
                break
        
        if not left_higher:
            continue
        
        # Check right bars
        right_higher = True
        right_max = 0
        for j in range(i + 1, i + right_bars + 1):
            right_val = df['high'].iloc[j]
            if pd.isna(right_val):
                right_higher = False
                break
            right_max = max(right_max, right_val)
            if current_high <= right_val:
                right_higher = False
                break
        
        if left_higher and right_higher:
            # Found a pivot high!
            confirmed_bar = i + right_bars
            shunted_index = confirmed_bar - shunt
            
            if 0 <= shunted_index < len(pivot_vals):
                pivot_vals[shunted_index] = current_high
                pivot_count += 1
                
                # Detailed logging for found pivots
                logging.info(f"✅ PIVOT HIGH FOUND!")
                logging.info(f"   📅 Date: {current_date}")
                logging.info(f"   📈 Value: {current_high:.2f}")
                logging.info(f"   📍 Position: i={i}, confirmed_bar={confirmed_bar}, shunted_index={shunted_index}")
                logging.info(f"   📊 Context: left_max={left_max:.2f}, current={current_high:.2f}, right_max={right_max:.2f}")
    
    logging.info(f"🎯 PIVOT HIGH RESULTS: Found {pivot_count} pivot highs out of {len(df)} bars")
    
    result = pd.Series(pivot_vals, index=df.index)
    non_nan_count = result.notna().sum()
    logging.info(f"📊 Final result: {non_nan_count} non-NaN pivot values")
    
    # Show found pivots
    pivot_values = result.dropna()
    if len(pivot_values) > 0:
        logging.info(f"📍 Found pivot highs:")
        for date, value in pivot_values.items():
            logging.info(f"   {date}: {value:.2f}")
    else:
        logging.warning("❌ No pivot highs found!")
    
    return result

def test_pivot_calculation():
    """Test pivot calculations with production data"""
    logging.info("🚀 Starting pivot calculation debug test")
    
    # Get database connection
    db_config = get_db_config()
    if not db_config:
        logging.error("❌ Cannot get database configuration")
        return
    
    try:
        conn = psycopg2.connect(**db_config)
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        
        # Get a sample stock with recent data
        sample_query = """
        SELECT symbol, COUNT(*) as record_count,
               MIN(date) as start_date, MAX(date) as end_date,
               MIN(high) as min_high, MAX(high) as max_high
        FROM price_daily 
        WHERE date >= CURRENT_DATE - INTERVAL '90 days'
        AND high > 0 AND volume > 0
        GROUP BY symbol
        HAVING COUNT(*) >= 30
        ORDER BY record_count DESC
        LIMIT 5
        """
        
        cursor.execute(sample_query)
        candidates = cursor.fetchall()
        
        logging.info(f"📋 Found {len(candidates)} candidate stocks:")
        for candidate in candidates:
            logging.info(f"   {candidate['symbol']}: {candidate['record_count']} records, "
                        f"{candidate['start_date']} to {candidate['end_date']}, "
                        f"high range {candidate['min_high']:.2f}-{candidate['max_high']:.2f}")
        
        if not candidates:
            logging.error("❌ No suitable stocks found for testing")
            return
        
        # Test with the first candidate
        test_symbol = candidates[0]['symbol']
        logging.info(f"🎯 Testing pivot calculations with {test_symbol}")
        
        # Get price data for the test symbol
        price_query = """
        SELECT date, open, high, low, close, volume
        FROM price_daily
        WHERE symbol = %s
        AND date >= CURRENT_DATE - INTERVAL '90 days'
        ORDER BY date ASC
        """
        
        cursor.execute(price_query, (test_symbol,))
        price_data = cursor.fetchall()
        
        logging.info(f"📊 Retrieved {len(price_data)} price records for {test_symbol}")
        
        # Convert to DataFrame
        df = pd.DataFrame(price_data)
        df['date'] = pd.to_datetime(df['date'])
        df.set_index('date', inplace=True)
        
        # Convert to numeric
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        
        logging.info(f"📋 DataFrame created with shape: {df.shape}")
        logging.info(f"📅 Date range: {df.index.min()} to {df.index.max()}")
        
        # Test pivot high calculation
        pivot_highs = pivot_high_debug(df, symbol=test_symbol)
        
        # Also test with different parameters
        logging.info("🔄 Testing with different parameters...")
        
        # Test with smaller parameters
        pivot_highs_small = pivot_high_debug(df, left_bars=2, right_bars=2, shunt=0, symbol=f"{test_symbol}_small")
        
        cursor.close()
        conn.close()
        
        logging.info("✅ Pivot calculation debug test completed")
        
    except Exception as e:
        logging.error(f"❌ Error in pivot calculation test: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_pivot_calculation()
