#!/usr/bin/env python3
"""
Populate current price and technical data for local testing
This script adds recent data to price_daily and technical_data_daily tables
"""

import psycopg2
from datetime import datetime, date, timedelta
import os
import random

def get_local_db_config():
    """Get local database configuration"""
    return {
        "host": "localhost",
        "port": 5432,
        "user": "postgres",
        "password": "password",
        "dbname": "stocks"
    }

def populate_recent_price_data(cur):
    """Populate recent price data"""
    print("Populating recent price data...")

    symbols = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'META', 'NVDA']

    # Create realistic price data for the last 30 days
    end_date = date.today()
    start_date = end_date - timedelta(days=30)

    base_prices = {
        'AAPL': 189.45,
        'MSFT': 420.75,
        'GOOGL': 138.45,
        'AMZN': 145.30,
        'TSLA': 235.00,
        'META': 485.20,
        'NVDA': 875.50
    }

    # Clear existing recent data
    cur.execute("DELETE FROM price_daily WHERE date >= %s", (start_date,))

    for symbol in symbols:
        base_price = base_prices[symbol]
        current_price = base_price

        current_date = start_date
        while current_date <= end_date:
            # Generate realistic daily price movement
            change_percent = random.uniform(-0.05, 0.05)  # -5% to +5%
            price_change = current_price * change_percent

            open_price = current_price
            high_price = open_price + abs(price_change) + random.uniform(0, open_price * 0.02)
            low_price = open_price - abs(price_change) - random.uniform(0, open_price * 0.02)
            close_price = open_price + price_change

            volume = random.randint(20000000, 80000000)

            cur.execute("""
                INSERT INTO price_daily
                (symbol, date, open, high, low, close, adj_close, volume, dividends, splits)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                symbol, current_date,
                round(open_price, 2), round(high_price, 2), round(low_price, 2),
                round(close_price, 2), round(close_price, 2),
                volume, 0.0, 0.0
            ))

            current_price = close_price
            current_date += timedelta(days=1)

    print(f"Inserted recent price data for {len(symbols)} symbols over 30 days")

def populate_recent_technical_data(cur):
    """Populate recent technical data"""
    print("Populating recent technical data...")

    symbols = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'META', 'NVDA']

    # Clear existing recent data
    today = date.today()
    cur.execute("DELETE FROM technical_data_daily WHERE date >= %s", (today - timedelta(days=30),))

    for symbol in symbols:
        # Generate realistic technical indicators for last few days
        for i in range(7):  # Last 7 days
            tech_date = today - timedelta(days=i)

            cur.execute("""
                INSERT INTO technical_data_daily
                (symbol, date, rsi, macd, macd_signal, macd_hist, mom, roc, adx, plus_di, minus_di,
                 atr, ad, cmf, mfi, td_sequential, td_combo, marketwatch, dm,
                 sma_10, sma_20, sma_50, sma_150, sma_200,
                 ema_4, ema_9, ema_21,
                 bbands_lower, bbands_middle, bbands_upper,
                 pivot_high, pivot_low, pivot_high_triggered, pivot_low_triggered)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                symbol, tech_date,
                round(random.uniform(30, 70), 2),  # RSI
                round(random.uniform(-2, 2), 4),   # MACD
                round(random.uniform(-2, 2), 4),   # MACD Signal
                round(random.uniform(-0.5, 0.5), 4),  # MACD Hist
                round(random.uniform(-5, 5), 2),   # Momentum
                round(random.uniform(-8, 8), 2),   # ROC
                round(random.uniform(20, 60), 2),  # ADX
                round(random.uniform(15, 35), 2),  # Plus DI
                round(random.uniform(15, 35), 2),  # Minus DI
                round(random.uniform(1, 4), 2),    # ATR
                random.randint(50000, 200000),     # AD
                round(random.uniform(-0.3, 0.3), 2),  # CMF
                round(random.uniform(20, 80), 2),  # MFI
                random.randint(1, 13),             # TD Sequential
                random.randint(1, 13),             # TD Combo
                round(random.uniform(0.2, 0.8), 2),  # Market Watch
                round(random.uniform(0.5, 2.5), 2),  # DM
                # Moving averages - realistic based on current prices
                round(random.uniform(180, 200), 2),  # SMA 10
                round(random.uniform(175, 195), 2),  # SMA 20
                round(random.uniform(170, 190), 2),  # SMA 50
                round(random.uniform(160, 180), 2),  # SMA 150
                round(random.uniform(150, 170), 2),  # SMA 200
                round(random.uniform(185, 195), 2),  # EMA 4
                round(random.uniform(180, 190), 2),  # EMA 9
                round(random.uniform(175, 185), 2),  # EMA 21
                # Bollinger Bands
                round(random.uniform(170, 180), 2),  # Lower
                round(random.uniform(180, 190), 2),  # Middle
                round(random.uniform(190, 200), 2),  # Upper
                # Pivots
                round(random.uniform(185, 195), 2),  # Pivot High
                round(random.uniform(175, 185), 2),  # Pivot Low
                round(random.uniform(0.1, 0.9), 2),  # Pivot High Triggered
                round(random.uniform(0.1, 0.9), 2)   # Pivot Low Triggered
            ))

    print(f"Inserted recent technical data for {len(symbols)} symbols over 7 days")

def main():
    print("Starting current data population...")

    try:
        # Connect to database
        conn = psycopg2.connect(**get_local_db_config())
        cur = conn.cursor()

        print("Connected to database successfully")

        # Populate data
        populate_recent_price_data(cur)
        populate_recent_technical_data(cur)

        # Commit changes
        conn.commit()
        print("✅ Successfully populated current test data!")

        # Verify data
        cur.execute("SELECT COUNT(*) FROM price_daily WHERE date >= %s", (date.today() - timedelta(days=30),))
        price_count = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM technical_data_daily WHERE date >= %s", (date.today() - timedelta(days=7),))
        tech_count = cur.fetchone()[0]

        print(f"\nData verification:")
        print(f"  Recent price records: {price_count}")
        print(f"  Recent technical records: {tech_count}")

        cur.close()
        conn.close()

    except Exception as error:
        print(f"❌ Error populating data: {error}")
        return False

    return True

if __name__ == "__main__":
    main()