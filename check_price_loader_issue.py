#!/usr/bin/env python3
import logging
logging.basicConfig(level=logging.WARNING)
from datetime import datetime, date
from utils.db.context import DatabaseContext

with DatabaseContext(role='read') as ctx:
    cursor = ctx.connection.cursor()

    print("=== INVESTIGATING PRICE LOADER GAP ===\n")

    # Check what data_loader_status says was loaded
    cursor.execute("""
        SELECT table_name, latest_date, symbols_loaded, row_count, completion_pct, status
        FROM data_loader_status
        WHERE table_name = 'price_daily'
        ORDER BY last_updated DESC LIMIT 1
    """)
    status_row = cursor.fetchone()
    if status_row:
        tbl, latest, syms, rows, pct, stat = status_row
        print(f"Loader Status for {latest}:")
        print(f"  Symbols loaded (claimed): {syms}")
        print(f"  Row count: {rows}")
        print(f"  Completion: {pct}%")
        print(f"  Status: {stat}")

    # Count actual symbols in DB for 2026-07-29
    cursor.execute("""
        SELECT COUNT(DISTINCT symbol) as unique_symbols,
               COUNT(*) as total_rows,
               COUNT(CASE WHEN close IS NULL THEN 1 END) as rows_with_null_close
        FROM price_daily
        WHERE date = '2026-07-29'
    """)
    actual = cursor.fetchone()
    if actual:
        print(f"\nActual data in price_daily for 2026-07-29:")
        print(f"  Unique symbols: {actual[0]}")
        print(f"  Total rows: {actual[1]}")
        print(f"  Rows with NULL close: {actual[2]}")

    # Check if there are partial rows or phantom rows
    cursor.execute("""
        SELECT symbol, open, high, low, close, volume, data_unavailable
        FROM price_daily
        WHERE date = '2026-07-29'
        LIMIT 20
    """)
    print(f"\nActual rows in price_daily for 2026-07-29:")
    for row in cursor.fetchall():
        print(f"  {row}")

    # Check what happened on 2026-07-28 (should be full load)
    cursor.execute("""
        SELECT COUNT(DISTINCT symbol) as unique_symbols, COUNT(*) as total_rows
        FROM price_daily
        WHERE date = '2026-07-28'
    """)
    result = cursor.fetchone()
    if result:
        print(f"\n2026-07-28 data (for comparison):")
        print(f"  Unique symbols: {result[0]}")
        print(f"  Total rows: {result[1]}")

    # Check loader execution history
    cursor.execute("""
        SELECT execution_started, execution_completed, symbols_loaded, completion_pct, status, error_message
        FROM data_loader_status
        WHERE table_name = 'price_daily'
        ORDER BY execution_completed DESC LIMIT 5
    """)
    print(f"\nLoader execution history:")
    for row in cursor.fetchall():
        started, completed, syms, pct, stat, err = row
        print(f"  {completed}: {syms} symbols, {pct}%, {stat}")
        if err:
            print(f"    Error: {err}")

    cursor.close()
