#!/usr/bin/env python3
from datetime import date

from utils.db.context import DatabaseContext

try:
    with DatabaseContext('read') as cur:
        # Check VIX data availability
        cur.execute('SELECT COUNT(*) FROM price_daily WHERE symbol = %s AND date >= %s', ('^VIX', date(2026, 6, 20)))
        count = cur.fetchone()[0]
        print(f'VIX records from 2026-06-20 onwards: {count}')

        # Get the latest VIX date
        cur.execute('SELECT MAX(date) FROM price_daily WHERE symbol = %s', ('^VIX',))
        latest = cur.fetchone()[0]
        print(f'Latest VIX date in database: {latest}')

        # Get recent dates from market_exposure
        cur.execute('SELECT DISTINCT date FROM market_exposure_daily WHERE date >= %s ORDER BY date DESC LIMIT 5', (date(2026, 6, 20),))
        dates = [row[0] for row in cur.fetchall()]
        print('\nRecent market_exposure dates:')
        for d in dates:
            print(f'  {d}')

except Exception as e:
    print(f'ERROR: {e}')
