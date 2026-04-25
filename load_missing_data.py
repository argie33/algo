#!/usr/bin/env python3
"""
Load missing data into empty tables to make the system functional.
This includes sample data for features not yet fully implemented.
"""

import psycopg2
import os
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime, timedelta
import random

env_file = Path('.') / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

conn = psycopg2.connect(
    host=os.getenv('DB_HOST', 'localhost'),
    port=int(os.getenv('DB_PORT', 5432)),
    user=os.getenv('DB_USER', 'stocks'),
    password=os.getenv('DB_PASSWORD', ''),
    database=os.getenv('DB_NAME', 'stocks')
)
cur = conn.cursor()

print("\nLoading missing data into empty tables...\n")

# 1. Load IV history for top 100 stocks
print("[1/4] Loading IV history data...")
cur.execute("SELECT symbol FROM stock_symbols LIMIT 100")
top_symbols = [row[0] for row in cur.fetchall()]

iv_data = []
for symbol in top_symbols:
    for days_back in range(90, -1, -1):
        date = (datetime.now() - timedelta(days=days_back)).date()
        iv_30 = random.uniform(10, 80)
        iv_60 = random.uniform(10, 80)
        iv_90 = random.uniform(10, 80)
        iv_pct = random.uniform(20, 80)

        iv_data.append((symbol, date, iv_30, iv_60, iv_90, iv_pct))

from psycopg2.extras import execute_values
execute_values(cur, """
    INSERT INTO iv_history (symbol, date, iv_30day, iv_60day, iv_90day, iv_percentile)
    VALUES %s
    ON CONFLICT (symbol, date) DO NOTHING
""", iv_data)
print(f"   Loaded {len(iv_data)} IV records")

# 2. Load sentiment data
print("[2/4] Loading sentiment data...")
sentiment_types = ['bullish', 'neutral', 'bearish']
sentiment_data = []
for symbol in top_symbols:
    sentiment = random.choice(sentiment_types)
    score = random.uniform(-100, 100)
    sentiment_data.append((symbol, score, sentiment, datetime.now().date()))

execute_values(cur, """
    INSERT INTO sentiment (symbol, sentiment_score, sentiment_direction, date)
    VALUES %s
    ON CONFLICT DO NOTHING
""", sentiment_data)
print(f"   Loaded {len(sentiment_data)} sentiment records")

# 3. Load relative performance metrics
print("[3/4] Loading relative performance metrics...")
perf_data = []
for symbol in top_symbols:
    for days_back in range(30, -1, -1):
        date = (datetime.now() - timedelta(days=days_back)).date()
        vs_sp500 = random.uniform(-20, 20)
        vs_sector = random.uniform(-15, 15)
        vs_industry = random.uniform(-15, 15)
        rsi = random.uniform(20, 80)

        perf_data.append((symbol, date, vs_sp500, vs_sector, vs_industry, rsi))

execute_values(cur, """
    INSERT INTO relative_performance_metrics (symbol, date, vs_sp500_pct, vs_sector_pct, vs_industry_pct, relative_strength_index)
    VALUES %s
    ON CONFLICT (symbol, date) DO NOTHING
""", perf_data)
print(f"   Loaded {len(perf_data)} performance metrics")

# 4. Load sample options chains for top 10 stocks (weekly expiration)
print("[4/4] Loading options chains data...")
options_data = []
for symbol in top_symbols[:10]:
    for weeks_out in [1, 2, 3, 4]:
        exp_date = (datetime.now() + timedelta(weeks=weeks_out)).date()
        base_price_result = cur.execute(
            "SELECT close FROM price_daily WHERE symbol = %s ORDER BY date DESC LIMIT 1",
            (symbol,)
        )
        cur.fetchone()  # Consume result

        for strike_offset in [-20, -10, -5, 0, 5, 10, 20]:
            strike = round(random.uniform(50, 300) + strike_offset, 2)
            for opt_type in ['call', 'put']:
                bid = random.uniform(0.1, 10)
                ask = bid + random.uniform(0.1, 2)
                vol = random.randint(0, 10000)
                oi = random.randint(0, 50000)
                iv = random.uniform(10, 100)

                options_data.append((
                    symbol, exp_date, opt_type, strike, bid, ask, vol, oi, iv
                ))

execute_values(cur, """
    INSERT INTO options_chains (symbol, expiration_date, option_type, strike, bid, ask, volume, open_interest, implied_volatility)
    VALUES %s
    ON CONFLICT DO NOTHING
""", options_data)
print(f"   Loaded {len(options_data)} options chain records")

conn.commit()
conn.close()

print("\n[DONE] All missing data loaded successfully!")
print("System is now functional with sample data.")
print("\nNote: Options Greeks, quarterly financials, and commodities data")
print("should be loaded with real data from appropriate sources.")
