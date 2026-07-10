#!/usr/bin/env python3
"""Check if data loaders are running and what's happening"""
from utils.db.context import DatabaseContext
from datetime import datetime, timedelta

# Check recent data_loader_runs to see what's being loaded
with DatabaseContext('read') as cur:
    cur.execute("""
        SELECT table_name, created_at, status
        FROM data_loader_runs
        WHERE created_at >= '2026-06-25'
        ORDER BY created_at DESC
        LIMIT 30
    """)
    runs = cur.fetchall()
    print("Data Loader Runs (from June 25 onwards):")
    for r in runs:
        print(f"  {r[0]:30s} {r[1]} {r[2]}")

    # Check what date range technical_data_daily covers
    cur.execute("""
        SELECT MIN(date) as min_date, MAX(date) as max_date, COUNT(*) as cnt
        FROM technical_data_daily
    """)
    tech_data = cur.fetchone()
    print(f"\ntechnical_data_daily coverage:")
    print(f"  Min date: {tech_data[0]}")
    print(f"  Max date: {tech_data[1]}")
    print(f"  Total rows: {tech_data[2]}")

    # Check what date range buy_sell_daily covers
    cur.execute("""
        SELECT MIN(date) as min_date, MAX(date) as max_date, COUNT(*) as cnt
        FROM buy_sell_daily
    """)
    buysell_data = cur.fetchone()
    print(f"\nbuy_sell_daily coverage:")
    print(f"  Min date: {buysell_data[0]}")
    print(f"  Max date: {buysell_data[1]}")
    print(f"  Total rows: {buysell_data[2]}")

    # Check price_daily date range
    cur.execute("""
        SELECT MIN(date) as min_date, MAX(date) as max_date, COUNT(*) as cnt
        FROM price_daily
    """)
    price_data = cur.fetchone()
    print(f"\nprice_daily coverage:")
    print(f"  Min date: {price_data[0]}")
    print(f"  Max date: {price_data[1]}")
    print(f"  Total rows: {price_data[2]}")

    # Check stock_scores date range
    cur.execute("""
        SELECT MIN(date) as min_date, MAX(date) as max_date, COUNT(*) as cnt
        FROM stock_scores
    """)
    scores_data = cur.fetchone()
    print(f"\nstock_scores coverage:")
    print(f"  Min date: {scores_data[0]}")
    print(f"  Max date: {scores_data[1]}")
    print(f"  Total rows: {scores_data[2]}")

    # Check market_exposure_daily
    cur.execute("""
        SELECT MIN(date) as min_date, MAX(date) as max_date, COUNT(*) as cnt
        FROM market_exposure_daily
    """)
    mkt_data = cur.fetchone()
    print(f"\nmarket_exposure_daily coverage:")
    print(f"  Min date: {mkt_data[0]}")
    print(f"  Max date: {mkt_data[1]}")
    print(f"  Total rows: {mkt_data[2]}")
