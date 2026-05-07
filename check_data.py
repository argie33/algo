#!/usr/bin/env python3
"""Check what data we have locally in the database."""

import psycopg2
import os
from pathlib import Path
from dotenv import load_dotenv
from datetime import date

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', 5432)),
    'user': os.getenv('DB_USER', 'stocks'),
    'password': os.getenv('DB_PASSWORD', ''),
    'database': os.getenv('DB_NAME', 'stocks'),
}

conn = psycopg2.connect(**DB_CONFIG)
cur = conn.cursor()

print('\nDATA FRESHNESS CHECK')
print('=' * 80)

# Check latest price data
cur.execute('''
    SELECT symbol, date, close, volume
    FROM price_daily
    ORDER BY date DESC
    LIMIT 1
''')
row = cur.fetchone()
if row:
    print(f'Latest price data:')
    print(f'  Symbol: {row[0]}')
    print(f'  Date: {row[1]}')
    print(f'  Close: ${row[2]:.2f}')
    print(f'  Volume: {row[3]:,}')
    print(f'  Age: {(date.today() - row[1]).days} days old')
else:
    print('NO price data in database')

# Check how many symbols
cur.execute('SELECT COUNT(DISTINCT symbol) FROM price_daily WHERE date >= CURRENT_DATE - INTERVAL \'30 days\'')
count = cur.fetchone()[0]
print(f'\nSymbols with data in last 30 days: {count}')

# Check swing trader scores
cur.execute('''
    SELECT symbol, swing_score, eval_date, pass_gates
    FROM swing_trader_scores
    ORDER BY eval_date DESC, swing_score DESC
    LIMIT 10
''')
scores = cur.fetchall()
print(f'\nTop 10 swing trader signals (latest):')
for score in scores:
    gates = 'PASS' if score[3] else 'FAIL'
    print(f'  {score[0]:6s}: score={score[1]:6.1f}  date={score[2]}  [{gates}]')

# Check today's data
today = date.today()
cur.execute('SELECT COUNT(*) FROM price_daily WHERE date = %s', (today,))
today_count = cur.fetchone()[0]
print(f'\nPrice records for TODAY ({today}): {today_count}')

# Latest date
cur.execute('SELECT MAX(date) FROM price_daily')
latest = cur.fetchone()[0]
print(f'Latest date with price data: {latest}')

# Algo evaluated signals
cur.execute('''
    SELECT symbol, swing_score, evaluation_date
    FROM algo_signals_evaluated
    ORDER BY evaluation_date DESC, swing_score DESC
    LIMIT 10
''')
eval_signals = cur.fetchall()
print(f'\nLatest algo-evaluated signals:')
for sig in eval_signals:
    print(f'  {sig[0]:6s}: score={sig[1]:6.1f}  date={sig[2]}')

cur.close()
conn.close()

print('\n' + '=' * 80)
print('DATA STATUS COMPLETE')
print('=' * 80 + '\n')
