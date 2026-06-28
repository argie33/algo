#!/usr/bin/env python3
"""Load missing VIX data for recent dates."""

import yfinance as yf

from utils.db.context import DatabaseContext

try:
    # Fetch VIX data for recent dates
    print("Fetching VIX data from yfinance...")
    vix = yf.download('^VIX', start='2026-06-24', end='2026-06-27', progress=False)

    print(f"Downloaded {len(vix)} VIX records:")
    print(vix[['Close', 'High', 'Low']])

    # Insert into price_daily table
    with DatabaseContext('write') as cur:
        for idx, row in vix.iterrows():
            trade_date = idx.date()
            close = float(row['Close'])
            high = float(row['High'])
            low = float(row['Low'])

            # Check if already exists
            cur.execute(
                'SELECT COUNT(*) FROM price_daily WHERE symbol = %s AND date = %s',
                ('^VIX', trade_date)
            )
            exists = cur.fetchone()[0] > 0

            if exists:
                print(f'  {trade_date}: Already exists, skipping')
            else:
                cur.execute(
                    'INSERT INTO price_daily (symbol, date, close, high, low, volume) VALUES (%s, %s, %s, %s, %s, 0)',
                    ('^VIX', trade_date, close, high, low)
                )
                print(f'  {trade_date}: Inserted (close={close:.2f})')

    print("\nVIX data loaded successfully!")

except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
