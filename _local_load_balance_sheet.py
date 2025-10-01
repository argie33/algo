#!/usr/bin/env python3
import os
import yfinance as yf
import psycopg2
from psycopg2.extras import execute_values

# Connect to database
conn = psycopg2.connect(
    host=os.getenv('DB_HOST', 'localhost'),
    port=int(os.getenv('DB_PORT', '5432')),
    user=os.getenv('DB_USER', 'postgres'),
    password=os.getenv('DB_PASSWORD', 'password'),
    dbname=os.getenv('DB_NAME', 'stocks')
)

cur = conn.cursor()

# Use a list of real symbols
symbols = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA', 'BRK.B', 'LLY', 'V']

print(f"Loading balance sheet data for {len(symbols)} symbols...")

for symbol in symbols:
    try:
        print(f"\n{'='*50}")
        print(f"Processing {symbol}...")
        
        ticker = yf.Ticker(symbol)
        bs = ticker.balance_sheet
        
        if bs is None or bs.empty:
            print(f"  ⚠️  No balance sheet data for {symbol}")
            continue
            
        print(f"  ✓ Got {len(bs.columns)} periods, {len(bs.index)} line items")
        
        # Prepare data for insertion
        data = []
        for date_col in bs.columns:
            date_str = date_col.strftime('%Y-%m-%d')
            for item_name in bs.index:
                value = bs.loc[item_name, date_col]
                if value is not None and not str(value).lower() in ['nan', 'none']:
                    try:
                        float_val = float(value)
                        data.append((symbol, date_str, str(item_name), float_val))
                    except (ValueError, TypeError):
                        pass
        
        if data:
            execute_values(
                cur,
                """
                INSERT INTO annual_balance_sheet (symbol, date, item_name, value)
                VALUES %s
                ON CONFLICT (symbol, date, item_name) DO UPDATE SET
                    value = EXCLUDED.value
                """,
                data
            )
            conn.commit()
            print(f"  ✓ Inserted {len(data)} records for {symbol}")
        else:
            print(f"  ⚠️  No valid data to insert for {symbol}")
            
    except Exception as e:
        print(f"  ❌ Error processing {symbol}: {e}")
        conn.rollback()

cur.close()
conn.close()

print(f"\n{'='*50}")
print("Balance sheet data loading complete!")
