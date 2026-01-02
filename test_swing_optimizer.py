#!/usr/bin/env python3
import os
from dotenv import load_dotenv
import psycopg2

load_dotenv('.env.local')

DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = os.getenv('DB_PORT', '5432')
DB_USER = os.getenv('DB_USER', 'stocks')
DB_PASSWORD = os.getenv('DB_PASSWORD')
DB_NAME = os.getenv('DB_NAME', 'stocks')

conn = psycopg2.connect(
    host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD, database=DB_NAME
)
cursor = conn.cursor()

# Check how many stocks qualify
cursor.execute("""
    SELECT COUNT(*) as total, 
           SUM(CASE WHEN composite_score IS NOT NULL THEN 1 ELSE 0 END) as with_score,
           SUM(CASE WHEN composite_score > 60 THEN 1 ELSE 0 END) as above_60,
           SUM(CASE WHEN composite_score > 50 THEN 1 ELSE 0 END) as above_50,
           MAX(composite_score) as max_score,
           MIN(composite_score) as min_score
    FROM stock_scores
""")
stats = cursor.fetchone()
print("\n📊 Stock Scores Statistics:")
print(f"  Total stocks: {stats[0]}")
print(f"  With composite score: {stats[1]}")
print(f"  Score > 60: {stats[2]}")
print(f"  Score > 50: {stats[3]}")
print(f"  Max score: {stats[4]}")
print(f"  Min score: {stats[5]}")

# Show top 20 stocks by score
print("\n🏆 Top 20 Stocks by Composite Score:")
cursor.execute("""
    SELECT ss.symbol, c.short_name, ss.composite_score, ss.quality_score, 
           ss.growth_score, ss.stability_score, ss.momentum_score, ss.value_score,
           (SELECT close FROM price_daily WHERE symbol = ss.symbol ORDER BY date DESC LIMIT 1) as current_price
    FROM stock_scores ss
    LEFT JOIN company_profile c ON ss.symbol = c.ticker
    WHERE ss.composite_score IS NOT NULL
    ORDER BY ss.composite_score DESC
    LIMIT 20
""")

for row in cursor.fetchall():
    print(f"  {row[0]:6} {row[1][:30]:30} Score: {row[2]:5.1f} Q:{row[3]:5.1f} G:{row[4]:5.1f} St:{row[5]:5.1f} Mo:{row[6]:5.1f} V:{row[7]:5.1f} Price: ${row[8]:.2f}")

cursor.close()
conn.close()
