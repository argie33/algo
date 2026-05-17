#!/usr/bin/env python3
import os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path('.env.local'))

import psycopg2

conn = psycopg2.connect(
    host=os.getenv('DB_HOST'),
    port=int(os.getenv('DB_PORT')),
    user=os.getenv('DB_USER'),
    password=os.getenv('DB_PASSWORD'),
    dbname=os.getenv('DB_NAME')
)
cur = conn.cursor()

tables_to_check = [
    ('stock_symbols', 'Master symbol list'),
    ('price_daily', 'Daily prices'),
    ('stock_scores', 'Composite scores'),
    ('buy_sell_daily', 'Buy/sell signals'),
    ('economic_data', 'Economic indicators'),
    ('market_health_daily', 'Market health'),
    ('fear_greed_index', 'Fear & Greed'),
    ('aaii_sentiment', 'AAII sentiment'),
    ('analyst_sentiment_analysis', 'Analyst sentiment'),
    ('quarterly_income_statement', 'Financial data'),
    ('key_metrics', 'Key metrics'),
    ('earnings_calendar', 'Earnings'),
]

print("\n=== DATA COMPLETENESS CHECK ===\n")
for table, desc in tables_to_check:
    try:
        cur.execute(f'SELECT COUNT(*) FROM {table}')
        count = cur.fetchone()[0]
        status = 'OK' if count > 0 else 'EMPTY'
        print(f'{status:6} {table:40} {count:8} rows   ({desc})')
    except Exception as e:
        print(f'ERROR  {table:40} {str(e)[:40]}')

conn.close()
