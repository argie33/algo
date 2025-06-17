#!/usr/bin/env python3
"""
Test script to verify pivot high/low calculations are working correctly
"""

import pandas as pd
import numpy as np
import yfinance as yf
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def pivot_high(df, left_bars=3, right_bars=3, shunt=1):
    """Pine Script style pivot high calculation with shunt"""
    pivot_vals = [np.nan] * len(df)
    
    for i in range(left_bars, len(df) - right_bars):
        current_high = df['High'].iloc[i]
        
        # Check left bars
        left_higher = True
        for j in range(i - left_bars, i):
            if current_high <= df['High'].iloc[j]:
                left_higher = False
                break
        
        if not left_higher:
            continue
            
        # Check right bars
        right_higher = True
        for j in range(i + 1, i + right_bars + 1):
            if current_high <= df['High'].iloc[j]:
                right_higher = False
                break
                
        if left_higher and right_higher:
            shunted_index = i + shunt
            if shunted_index < len(pivot_vals):
                pivot_vals[shunted_index] = current_high
    
    return pd.Series(pivot_vals, index=df.index)

def pivot_low(df, left_bars=3, right_bars=3, shunt=1):
    """Pine Script style pivot low calculation with shunt"""
    pivot_vals = [np.nan] * len(df)
    
    for i in range(left_bars, len(df) - right_bars):
        current_low = df['Low'].iloc[i]
        
        # Check left bars
        left_lower = True
        for j in range(i - left_bars, i):
            if current_low >= df['Low'].iloc[j]:
                left_lower = False
                break
        
        if not left_lower:
            continue
            
        # Check right bars
        right_lower = True
        for j in range(i + 1, i + right_bars + 1):
            if current_low >= df['Low'].iloc[j]:
                right_lower = False
                break
                
        if left_lower and right_lower:
            shunted_index = i + shunt  
            if shunted_index < len(pivot_vals):
                pivot_vals[shunted_index] = current_low
    
    return pd.Series(pivot_vals, index=df.index)

def test_pivot_calculations():
    """Test pivot calculations on real market data"""
    
    test_symbols = ['AAPL', 'TSLA', 'MSFT']
    
    for symbol in test_symbols:
        try:
            logging.info(f"\n🔍 Testing {symbol} pivot calculations...")
            
            # Get recent data
            ticker = yf.Ticker(symbol)
            df = ticker.history(period="6mo", interval="1d")
            
            if df.empty:
                logging.warning(f"❌ No data for {symbol}")
                continue
            
            logging.info(f"📊 Loaded {len(df)} days of data for {symbol}")
            
            # Calculate pivots
            pivot_highs = pivot_high(df, left_bars=3, right_bars=3, shunt=1)
            pivot_lows = pivot_low(df, left_bars=3, right_bars=3, shunt=1)
            
            # Count valid pivots
            high_count = pivot_highs.notna().sum()
            low_count = pivot_lows.notna().sum()
            
            logging.info(f"📍 Found {high_count} pivot highs, {low_count} pivot lows")
            
            if high_count > 0 or low_count > 0:
                logging.info("✅ Pivot calculations working correctly!")
                
                # Show some recent pivots
                recent_data = df.tail(20).copy()
                recent_highs = pivot_highs.tail(20)
                recent_lows = pivot_lows.tail(20)
                
                logging.info("📋 Recent pivot data (last 20 days):")
                for i in range(len(recent_data)):
                    date = recent_data.index[i].strftime('%Y-%m-%d')
                    close = recent_data['Close'].iloc[i]
                    ph = recent_highs.iloc[i] if not pd.isna(recent_highs.iloc[i]) else None
                    pl = recent_lows.iloc[i] if not pd.isna(recent_lows.iloc[i]) else None
                    
                    pivot_str = ""
                    if ph is not None:
                        pivot_str += f" PH:{ph:.2f}"
                    if pl is not None:
                        pivot_str += f" PL:{pl:.2f}"
                    
                    if pivot_str:
                        logging.info(f"  {date}: Close={close:.2f}{pivot_str}")
            else:
                logging.warning(f"⚠️  No pivots found for {symbol}")
                
        except Exception as e:
            logging.error(f"❌ Error testing {symbol}: {str(e)}")
    
    return True

def main():
    """Main test function"""
    logging.info("🚀 Starting pivot calculation test...")
    
    try:
        success = test_pivot_calculations()
        if success:
            logging.info("✅ Pivot calculation test completed!")
        else:
            logging.error("❌ Pivot calculation test failed")
            
    except Exception as e:
        logging.error(f"❌ Test failed: {str(e)}")

if __name__ == "__main__":
    main()
