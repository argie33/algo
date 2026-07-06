#!/usr/bin/env python3
"""Check market_sentiment table."""

import psycopg2
import os

try:
    conn = psycopg2.connect(
        host=os.environ.get('DB_HOST', 'localhost'),
        user=os.environ.get('DB_USER', 'algo'),
        password=os.environ.get('DB_PASSWORD', 'algo'),
        database=os.environ.get('DB_NAME', 'algo'),
        connect_timeout=5
    )
    cur = conn.cursor()

    # Check if table exists
    cur.execute("SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name='market_sentiment')")
    exists = cur.fetchone()[0]
    print(f'[INFO] market_sentiment table exists: {exists}')

    if exists:
        # Get columns
        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name='market_sentiment'")
        cols = [row[0] for row in cur.fetchall()]
        print(f'[INFO] Columns: {cols}')

        # Check row count
        cur.execute('SELECT COUNT(*) FROM market_sentiment')
        count = cur.fetchone()[0]
        print(f'[INFO] Row count: {count}')

        # Check required columns
        required = ['date', 'fear_greed_index', 'sentiment_score', 'bullish_pct', 'bearish_pct', 'neutral_pct']
        missing = [c for c in required if c not in cols]
        if missing:
            print(f'[ERROR] Missing columns: {missing}')
        else:
            print('[OK] All required columns present')
    else:
        print('[ERROR] market_sentiment table does not exist!')

    conn.close()

except Exception as e:
    print(f'[ERROR] {type(e).__name__}: {e}')
