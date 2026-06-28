#!/usr/bin/env python3
"""Check AWS health status after deployment."""
import os
import psycopg2
import psycopg2.extras
from datetime import date, timedelta

try:
    conn = psycopg2.connect(
        host=os.environ.get('DB_HOST', 'localhost'),
        port=int(os.environ.get('DB_PORT', '5432')),
        database=os.environ.get('DB_NAME', 'algo_trading'),
        user=os.environ.get('DB_USER', 'algo_user'),
        password=os.environ.get('DB_PASSWORD', '')
    )

    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Get all loaders except pipeline-removed ones
    pipeline_removed = {'technical_data_daily', 'buy_sell_daily', 'signal_quality_scores'}
    cur.execute("SELECT table_name, last_updated FROM data_loader_status WHERE table_name NOT IN (%s, %s, %s) ORDER BY table_name",
                tuple(pipeline_removed))
    rows = cur.fetchall()

    from algo.infrastructure import MarketCalendar
    today = date.today()
    expected_date = today - timedelta(days=1)
    for _ in range(10):
        if MarketCalendar.is_trading_day(expected_date):
            break
        expected_date -= timedelta(days=1)

    ok = stale = 0
    fresh_tables = []
    stale_tables = []

    for row in rows:
        last_updated = row['last_updated']
        table_name = row['table_name']
        if not last_updated or (last_updated.date() if hasattr(last_updated, 'date') else last_updated) < expected_date:
            stale += 1
            stale_tables.append(table_name)
        else:
            ok += 1
            fresh_tables.append(table_name)

    print(f"\n{'='*60}")
    print(f"AWS DASHBOARD HEALTH STATUS")
    print(f"{'='*60}")
    print(f"Freshness: {ok}/{ok+stale} fresh  {stale} stale")
    print(f"Status: {'[OK] READY' if ok == len(rows) else '[WARN] NOT READY'}")
    print(f"\nFresh tables ({ok}): {', '.join(fresh_tables[:5])}{'...' if len(fresh_tables) > 5 else ''}")
    if stale_tables:
        print(f"Stale tables ({stale}): {', '.join(stale_tables[:5])}{'...' if len(stale_tables) > 5 else ''}")
    print(f"{'='*60}\n")

    cur.close()
    conn.close()
except Exception as e:
    print(f"Error: {type(e).__name__}: {e}")
