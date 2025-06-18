#!/usr/bin/env python3
"""
Quick script to check pivot data in database
"""
import psycopg2
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Database connection
def get_db_connection():
    return psycopg2.connect(
        host=os.getenv('DB_HOST'),
        database=os.getenv('DB_NAME'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD'),
        port=os.getenv('DB_PORT', 5432)
    )

# Check pivot data for a specific symbol
def check_pivot_data(symbol='AAPL', limit=20):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Get recent data for the symbol
        query = """
        SELECT 
            symbol, date, 
            pivot_high, pivot_low,
            rsi, macd  -- Include other indicators for comparison
        FROM technical_data_daily 
        WHERE symbol = %s 
        ORDER BY date DESC 
        LIMIT %s
        """
        
        cur.execute(query, (symbol, limit))
        results = cur.fetchall()
        
        print(f"Checking pivot data for {symbol} (last {limit} records):")
        print("-" * 80)
        print(f"{'Date':<12} {'Pivot High':<12} {'Pivot Low':<12} {'RSI':<8} {'MACD':<8}")
        print("-" * 80)
        
        pivot_high_count = 0
        pivot_low_count = 0
        
        for row in results:
            symbol, date, pivot_high, pivot_low, rsi, macd = row
            
            # Count non-null pivots
            if pivot_high is not None:
                pivot_high_count += 1
            if pivot_low is not None:
                pivot_low_count += 1
                
            # Format values for display
            ph = f"{pivot_high:.2f}" if pivot_high is not None else "None"
            pl = f"{pivot_low:.2f}" if pivot_low is not None else "None"
            rsi_val = f"{rsi:.2f}" if rsi is not None else "None"
            macd_val = f"{macd:.4f}" if macd is not None else "None"
            
            print(f"{date} {ph:<12} {pl:<12} {rsi_val:<8} {macd_val:<8}")
        
        print("-" * 80)
        print(f"Summary: {pivot_high_count} pivot highs, {pivot_low_count} pivot lows out of {len(results)} records")
        
        cur.close()
        conn.close()
        
    except Exception as e:
        print(f"Error checking pivot data: {e}")

if __name__ == "__main__":
    check_pivot_data('AAPL', 30)
