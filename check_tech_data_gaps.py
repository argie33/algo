#!/usr/bin/env python3
"""Check for data gaps in technical_data_daily"""
from utils.db.context import DatabaseContext
from datetime import date, timedelta

with DatabaseContext('read') as cur:
    # Check technical_data_daily date range and counts
    print("1. Technical data daily coverage (June 25 - July 6):")
    cur.execute("""
        SELECT date, COUNT(DISTINCT symbol) as symbol_count
        FROM technical_data_daily
        WHERE date >= '2026-06-25' AND date <= '2026-07-06'
        GROUP BY date
        ORDER BY date DESC
    """)
    for row in cur.fetchall():
        print(f"   {row[0]}: {row[1]} symbols")

    # Check for gaps in the data
    print("\n2. Checking for missing trading days in technical_data_daily:")
    cur.execute("""
        WITH dates AS (
            SELECT DISTINCT date FROM technical_data_daily
            WHERE date >= '2026-06-20' AND date <= '2026-07-06'
            ORDER BY date
        )
        SELECT
            date,
            (date - LAG(date) OVER (ORDER BY date)) as gap_days
        FROM dates
        ORDER BY date DESC
    """)
    prev_date = None
    for row in cur.fetchall():
        date_val, gap_days = row
        if gap_days and (hasattr(gap_days, 'days') and gap_days.days > 1 or isinstance(gap_days, int) and gap_days > 1):
            gap_count = gap_days.days if hasattr(gap_days, 'days') else gap_days
            print(f"   GAP: {gap_count} days between {prev_date} and {date_val}")
        prev_date = date_val

    # Check buy_sell_daily source: are signals coming from technical data?
    print("\n3. Signal generation pattern (buy_sell_daily):")
    cur.execute("""
        SELECT date, signal, COUNT(*) as count
        FROM buy_sell_daily
        WHERE date >= '2026-06-25' AND date <= '2026-07-06'
        GROUP BY date, signal
        ORDER BY date DESC, signal
    """)
    for row in cur.fetchall():
        print(f"   {row[0]} {row[1]}: {row[2]} signals")

    # Count unique symbols with signals per day
    print("\n4. Unique symbols with signals per day:")
    cur.execute("""
        SELECT date, COUNT(DISTINCT symbol) as unique_symbols
        FROM buy_sell_daily
        WHERE date >= '2026-06-25' AND date <= '2026-07-06'
        GROUP BY date
        ORDER BY date DESC
    """)
    for row in cur.fetchall():
        print(f"   {row[0]}: {row[1]} unique symbols")

    # Check if technical data has the required indicator fields
    print("\n5. Sample technical data completeness (July 6):")
    cur.execute("""
        SELECT
            symbol,
            COUNT(*) as rows,
            COUNT(CASE WHEN open IS NOT NULL THEN 1 END) as has_open,
            COUNT(CASE WHEN high IS NOT NULL THEN 1 END) as has_high,
            COUNT(CASE WHEN low IS NOT NULL THEN 1 END) as has_low,
            COUNT(CASE WHEN close IS NOT NULL THEN 1 END) as has_close,
            COUNT(CASE WHEN sma_50 IS NOT NULL THEN 1 END) as has_sma50,
            COUNT(CASE WHEN sma_200 IS NOT NULL THEN 1 END) as has_sma200
        FROM technical_data_daily
        WHERE date = '2026-07-06'
        LIMIT 5
    """)
    cols = cur.fetchone()
    print(f"   Sample row counts (OHLC, SMA):")
    if cols:
        print(f"   Total rows: {cols[0]}, OHLC: ({cols[1]}, {cols[2]}, {cols[3]}, {cols[4]}), SMA: ({cols[5]}, {cols[6]})")
