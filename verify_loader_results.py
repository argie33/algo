#!/usr/bin/env python3
"""Verify that loaders have populated data successfully."""

import os
import sys
from datetime import datetime, timedelta

os.environ['DB_NAME'] = 'stocks'
os.environ['DB_USER'] = 'stocks'
sys.path.insert(0, '.')

from utils.db import get_db_connection

def verify_loaders():
    """Check status and row counts for all loaders."""
    db = get_db_connection()
    cursor = db.cursor()

    # Check loader status
    cursor.execute('''
    SELECT table_name, status, row_count, symbol_count, completion_pct, last_updated
    FROM data_loader_status
    ORDER BY last_updated DESC
    LIMIT 50
    ''')

    print("=" * 120)
    print(f"LOADER STATUS VERIFICATION - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 120)
    print()

    # Group by status
    completed = []
    running = []
    failed = []

    for row in cursor.fetchall():
        table_name, status, rows, symbols, pct, updated = row
        entry = {
            'table': table_name,
            'rows': rows or 0,
            'symbols': symbols or 0,
            'pct': f'{pct:.1f}%' if pct else 'N/A',
            'updated': updated.strftime('%Y-%m-%d %H:%M') if updated else 'N/A'
        }

        if status == 'COMPLETED':
            completed.append(entry)
        elif status == 'RUNNING':
            running.append(entry)
        else:
            failed.append(entry)

    # Display results
    print(f"COMPLETED ({len(completed)} loaders):")
    print(f"{'Table':40} {'Rows':12} {'Symbols':10} {'%':8} {'Updated':20}")
    print("-" * 90)
    for e in sorted(completed, key=lambda x: x['table']):
        print(f"{e['table']:40} {e['rows']:12d} {e['symbols']:10d} {e['pct']:8} {e['updated']:20}")

    print()
    print(f"RUNNING ({len(running)} loaders):")
    for e in sorted(running, key=lambda x: x['table']):
        print(f"  {e['table']}")

    if failed:
        print()
        print(f"FAILED ({len(failed)} loaders):")
        for e in sorted(failed, key=lambda x: x['table']):
            print(f"  {e['table']}")

    print()
    print("=" * 120)

    # Check critical tables for data
    print()
    print("CRITICAL DATA CHECKS:")
    print("-" * 120)

    critical_tables = [
        ('price_daily', 'symbol, date'),
        ('technical_data_daily', 'symbol, date'),
        ('earnings_calendar', 'symbol, date'),
        ('buy_sell_daily', 'symbol, date'),
        ('annual_income_statement', 'symbol, period_ending'),
        ('quarterly_income_statement', 'symbol, period_ending'),
        ('momentum_metrics', 'symbol, date'),
        ('stability_metrics', 'symbol, date'),
    ]

    for table, groupby in critical_tables:
        cursor.execute(f'''
        SELECT COUNT(*) as total, COUNT(DISTINCT symbol) as unique_symbols, MAX(date) as max_date
        FROM {table}
        LIMIT 1
        ''')
        result = cursor.fetchone()
        if result:
            total, unique_syms, max_date = result
            max_date_str = max_date.strftime('%Y-%m-%d') if max_date else 'N/A'
            print(f"{table:40} {total:10d} rows | {unique_syms:5d} symbols | max_date={max_date_str}")
        else:
            print(f"{table:40} NO DATA")

    cursor.close()
    db.close()

    print()
    print("=" * 120)

if __name__ == '__main__':
    verify_loaders()
