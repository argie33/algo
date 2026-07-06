#!/usr/bin/env python3
"""Check technical data coverage for July 6 (the issue)"""
from utils.db.context import DatabaseContext
from datetime import date, timedelta

target_date = date(2026, 7, 6)
lookback_window = 10  # days

with DatabaseContext('read') as cur:
    # Get price_daily coverage on target date
    cur.execute("""
        SELECT COUNT(DISTINCT symbol)
        FROM price_daily
        WHERE date = %s
    """, (target_date,))
    price_coverage = cur.fetchone()[0]
    print(f"1. Price coverage on {target_date}: {price_coverage} symbols")

    # Get technical_data_daily coverage within lookback window
    cur.execute("""
        SELECT COUNT(DISTINCT symbol), MAX(date)
        FROM technical_data_daily
        WHERE date >= %s AND date <= %s
    """, (target_date - timedelta(days=lookback_window), target_date))
    result = cur.fetchone()
    tech_coverage = result[0]
    tech_max_date = result[1]
    print(f"2. Tech coverage within {lookback_window} days of {target_date}: {tech_coverage} symbols (max date: {tech_max_date})")

    # Calculate coverage percentage
    if price_coverage > 0:
        coverage_pct = (tech_coverage / price_coverage) * 100
        print(f"3. Coverage percentage: {coverage_pct:.1f}%")
        print(f"4. Min required: 95.0%")
        print(f"5. Would loader PASS? {coverage_pct >= 95.0}")

    # Check all recent dates
    print(f"\n6. Technical coverage by date (last 10 days):")
    cur.execute("""
        SELECT date, COUNT(DISTINCT symbol)
        FROM technical_data_daily
        WHERE date >= %s AND date <= %s
        GROUP BY date
        ORDER BY date DESC
    """, (target_date - timedelta(days=10), target_date))
    for row in cur.fetchall():
        date_val, cnt = row
        if price_coverage > 0:
            pct = (cnt / price_coverage) * 100
            print(f"   {date_val}: {cnt} symbols ({pct:.1f}%)")
        else:
            print(f"   {date_val}: {cnt} symbols")

    # When was the last day with high coverage?
    print(f"\n7. Looking backwards for last date with >95% coverage:")
    cur.execute("""
        SELECT date, COUNT(DISTINCT symbol)
        FROM technical_data_daily
        WHERE date < %s
        GROUP BY date
        ORDER BY date DESC
        LIMIT 30
    """, (target_date,))
    for row in cur.fetchall():
        date_val, cnt = row
        if price_coverage > 0:
            pct = (cnt / price_coverage) * 100
            status = "OK" if pct >= 95.0 else "FAIL"
            print(f"   {date_val}: {cnt} ({pct:.1f}%) [{status}]")
            if pct >= 95.0:
                break
