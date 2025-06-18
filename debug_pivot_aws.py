import os
import psycopg2
import pandas as pd
from datetime import datetime, timedelta

# Use AWS database configuration
def get_db_connection():
    try:
        # AWS RDS connection
        db_config = {
            'host': 'fundamentals-db.c8mnl2lkdckh.us-east-1.rds.amazonaws.com',
            'database': 'fundamentals',
            'user': 'fundamentals_user',
            'password': 'funddata2024!',
            'port': '5432'
        }
        
        print(f"Attempting to connect to AWS RDS: {db_config['host']}:{db_config['port']}/{db_config['database']}")
        
        conn = psycopg2.connect(**db_config)
        return conn
    except Exception as e:
        print(f"AWS Database connection failed: {e}")
        return None

# Copy pivot calculation functions from loadtechnicalsdaily.py
def pivot_high(df, window=14):
    """Calculate pivot highs"""
    if len(df) < window * 2 + 1:
        print(f"Not enough data for pivot high calculation: {len(df)} rows, need {window * 2 + 1}")
        return [None] * len(df)
    
    highs = df['high'].values
    pivot_highs = [None] * len(df)
    
    for i in range(window, len(df) - window):
        current_high = highs[i]
        is_pivot = True
        
        # Check left side
        for j in range(i - window, i):
            if highs[j] >= current_high:
                is_pivot = False
                break
        
        # Check right side
        if is_pivot:
            for j in range(i + 1, i + window + 1):
                if highs[j] >= current_high:
                    is_pivot = False
                    break
        
        if is_pivot:
            pivot_highs[i] = current_high
    
    return pivot_highs

def pivot_low(df, window=14):
    """Calculate pivot lows"""
    if len(df) < window * 2 + 1:
        print(f"Not enough data for pivot low calculation: {len(df)} rows, need {window * 2 + 1}")
        return [None] * len(df)
    
    lows = df['low'].values
    pivot_lows = [None] * len(df)
    
    for i in range(window, len(df) - window):
        current_low = lows[i]
        is_pivot = True
        
        # Check left side
        for j in range(i - window, i):
            if lows[j] <= current_low:
                is_pivot = False
                break
        
        # Check right side
        if is_pivot:
            for j in range(i + 1, i + window + 1):
                if lows[j] <= current_low:
                    is_pivot = False
                    break
        
        if is_pivot:
            pivot_lows[i] = current_low
    
    return pivot_lows

def test_pivot_calculations():
    """Test pivot calculations with actual AWS database data"""
    conn = get_db_connection()
    if not conn:
        print("❌ Cannot connect to AWS database")
        return
    
    print("✅ Connected to AWS database successfully")
    
    try:
        # Get a sample of recent data for a few symbols
        cursor = conn.cursor()
        
        print("\n🔍 Getting sample symbols with recent data...")
        cursor.execute("""
            SELECT symbol, COUNT(*) as days
            FROM price_daily 
            WHERE date >= CURRENT_DATE - INTERVAL '60 days'
            GROUP BY symbol
            HAVING COUNT(*) >= 30
            ORDER BY COUNT(*) DESC
            LIMIT 5
        """)
        
        symbols = cursor.fetchall()
        print(f"Found {len(symbols)} symbols with sufficient data:")
        for symbol, days in symbols:
            print(f"  {symbol}: {days} days")
        
        # Test pivot calculations for each symbol
        for symbol, days in symbols[:2]:  # Test first 2 symbols
            print(f"\n📊 Testing pivot calculations for {symbol} ({days} days of data)")
            
            cursor.execute("""
                SELECT date, open, high, low, close, volume
                FROM price_daily
                WHERE symbol = %s AND date >= CURRENT_DATE - INTERVAL '60 days'
                ORDER BY date ASC
            """, (symbol,))
            
            rows = cursor.fetchall()
            
            if len(rows) < 30:
                print(f"  ❌ Insufficient data: {len(rows)} rows")
                continue
            
            # Create DataFrame
            df = pd.DataFrame(rows, columns=['date', 'open', 'high', 'low', 'close', 'volume'])
            df['date'] = pd.to_datetime(df['date'])
            
            print(f"  📈 Data range: {df['date'].min()} to {df['date'].max()}")
            print(f"  📊 Price range: ${df['low'].min():.2f} - ${df['high'].max():.2f}")
            
            # Test pivot calculations
            print("  🔄 Calculating pivot highs...")
            pivot_highs = pivot_high(df, window=14)
            
            print("  🔄 Calculating pivot lows...")  
            pivot_lows = pivot_low(df, window=14)
            
            # Count non-null pivots
            high_count = sum(1 for x in pivot_highs if x is not None)
            low_count = sum(1 for x in pivot_lows if x is not None)
            
            print(f"  📊 Results:")
            print(f"    Pivot Highs found: {high_count}")
            print(f"    Pivot Lows found: {low_count}")
            
            if high_count > 0:
                valid_highs = [x for x in pivot_highs if x is not None]
                print(f"    Highest pivot: ${max(valid_highs):.2f}")
                print(f"    Average pivot high: ${sum(valid_highs)/len(valid_highs):.2f}")
            
            if low_count > 0:
                valid_lows = [x for x in pivot_lows if x is not None]
                print(f"    Lowest pivot: ${min(valid_lows):.2f}")
                print(f"    Average pivot low: ${sum(valid_lows)/len(valid_lows):.2f}")
            
            # Show some sample data points
            print(f"  📋 Sample data (first 5 rows):")
            for i in range(min(5, len(df))):
                row = df.iloc[i]
                ph = pivot_highs[i] if pivot_highs[i] is not None else "N/A"
                pl = pivot_lows[i] if pivot_lows[i] is not None else "N/A"
                print(f"    {row['date'].strftime('%Y-%m-%d')}: H=${row['high']:.2f} L=${row['low']:.2f} PH={ph} PL={pl}")
            
            print(f"  📋 Sample data (last 5 rows):")
            for i in range(max(0, len(df)-5), len(df)):
                row = df.iloc[i]
                ph = pivot_highs[i] if pivot_highs[i] is not None else "N/A"
                pl = pivot_lows[i] if pivot_lows[i] is not None else "N/A"
                print(f"    {row['date'].strftime('%Y-%m-%d')}: H=${row['high']:.2f} L=${row['low']:.2f} PH={ph} PL={pl}")
    
    except Exception as e:
        print(f"❌ Error during pivot testing: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        if conn:
            conn.close()
            print("\n🔒 Database connection closed")

if __name__ == "__main__":
    print("🚀 Starting AWS pivot calculation debug...")
    print("=" * 60)
    test_pivot_calculations()
    print("=" * 60)
    print("✅ Debug complete!")
