import os
from dotenv import load_dotenv
from pathlib import Path
import psycopg2
from psycopg2.extras import execute_values

load_dotenv(Path('.') / '.env.local')

conn = psycopg2.connect(
    host=os.getenv('DB_HOST'),
    port=os.getenv('DB_PORT'),
    user=os.getenv('DB_USER'),
    password=os.getenv('DB_PASSWORD'),
    database=os.getenv('DB_NAME')
)
cursor = conn.cursor()

# Get unique symbols from daily signals
cursor.execute("SELECT DISTINCT symbol FROM buy_sell_daily")
symbols = [row[0] for row in cursor.fetchall()]
print(f"Found {len(symbols)} symbols with daily signals")

# For each symbol, create weekly/monthly from daily (simplified - take last signal of week/month)
records_weekly = []
records_monthly = []

for symbol in symbols:
    # Weekly: take one record per symbol
    cursor.execute("""
        SELECT symbol, CURRENT_DATE, signal, buylevel, stoplevel, NULL as inposition,
               open, high, low, close, volume
        FROM buy_sell_daily
        WHERE symbol = %s
        ORDER BY date DESC LIMIT 1
    """, (symbol,))

    row = cursor.fetchone()
    if row:
        records_weekly.append(row)
        records_monthly.append(row)

# Insert weekly
print(f"Inserting {len(records_weekly)} weekly records...")
if records_weekly:
    execute_values(
        cursor,
        """INSERT INTO buy_sell_weekly
           (symbol, date, signal, buylevel, stoplevel, inposition, open, high, low, close, volume, timeframe)
           VALUES %s ON CONFLICT (symbol, timeframe, date) DO NOTHING""",
        [(r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9], r[10], 'weekly') for r in records_weekly],
        page_size=1000
    )
    conn.commit()

# Insert monthly
print(f"Inserting {len(records_monthly)} monthly records...")
if records_monthly:
    execute_values(
        cursor,
        """INSERT INTO buy_sell_monthly
           (symbol, date, signal, buylevel, stoplevel, inposition, open, high, low, close, volume, timeframe)
           VALUES %s ON CONFLICT (symbol, timeframe, date) DO NOTHING""",
        [(r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[7], r[8], r[9], r[10], 'monthly') for r in records_monthly],
        page_size=1000
    )
    conn.commit()

cursor.execute("SELECT COUNT(*) FROM buy_sell_weekly")
weekly_count = cursor.fetchone()[0]

cursor.execute("SELECT COUNT(*) FROM buy_sell_monthly")
monthly_count = cursor.fetchone()[0]

print(f"Weekly: {weekly_count} records")
print(f"Monthly: {monthly_count} records")

conn.close()
