#!/usr/bin/env python3
"""
Monitor morning prep pipeline data freshness for 8 critical tables.
Checks if data is <1 day old and has >=90% symbol coverage.
Runs every 5 minutes until data is fresh or Monday 5 PM ET.
"""

import os
import sys
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
import psycopg2
from psycopg2.extras import RealDictCursor
import pytz

# Fix encoding for Windows
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Get database credentials from environment
def get_db_config():
    return {
        'host': os.getenv('DB_HOST', 'localhost'),
        'port': int(os.getenv('DB_PORT', 5432)),
        'database': os.getenv('DB_NAME', 'algo'),
        'user': os.getenv('DB_USER', 'postgres'),
        'password': os.getenv('DB_PASSWORD', ''),
    }

# 8 critical tables for morning prep pipeline
CRITICAL_TABLES = [
    'price_daily',
    'technical_data_daily',
    'buy_sell_daily',
    'signal_quality_scores',
    'swing_trader_scores',
    'market_health_daily',
    'trend_template_data',
    'sector_ranking',
]

def connect_db():
    """Connect to PostgreSQL database."""
    try:
        config = get_db_config()
        conn = psycopg2.connect(**config)
        return conn
    except Exception as e:
        print(f"[ERROR] Database connection failed: {e}")
        return None

def get_table_freshness(conn, table_name):
    """
    Check table freshness: max date, row count, symbol coverage.
    Returns: {
        'table': str,
        'max_date': date,
        'age_hours': float,
        'is_fresh': bool,
        'symbol_count': int,
        'coverage_pct': float,
        'error': str or None
    }
    """
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # Different queries for different table structures
            if table_name == 'sector_ranking':
                # sector_ranking uses 'date' column and sector_name
                cur.execute(f"""
                    SELECT
                        MAX(date)::TEXT as max_date,
                        COUNT(DISTINCT sector_name) as sector_count
                    FROM {table_name}
                """)
                result = cur.fetchone()
                max_date_str = result['max_date']
                symbol_count = result['sector_count'] or 0
            elif table_name == 'market_health_daily':
                # market_health_daily has no symbol column, just one row per date
                cur.execute(f"""
                    SELECT
                        MAX(date)::TEXT as max_date,
                        COUNT(*) as row_count
                    FROM {table_name}
                """)
                result = cur.fetchone()
                max_date_str = result['max_date']
                symbol_count = 1  # Just track if it has recent data
            else:
                # All other tables use 'symbol' and 'date' columns
                cur.execute(f"""
                    SELECT
                        MAX(date)::TEXT as max_date,
                        COUNT(DISTINCT symbol) as symbol_count
                    FROM {table_name}
                """)
                result = cur.fetchone()
                max_date_str = result['max_date']
                symbol_count = result['symbol_count'] or 0

            if not max_date_str:
                return {
                    'table': table_name,
                    'max_date': None,
                    'age_hours': float('inf'),
                    'is_fresh': False,
                    'symbol_count': 0,
                    'coverage_pct': 0.0,
                    'error': 'No data in table'
                }

            # Parse date and calculate age
            max_date = datetime.strptime(max_date_str, '%Y-%m-%d').date()
            now = datetime.now().date()
            age_days = (now - max_date).days
            age_hours = age_days * 24

            # Data is fresh if <24 hours old
            is_fresh = age_hours < 24

            # Calculate coverage
            if table_name in ['market_health_daily', 'sector_ranking']:
                # These tables are considered "fresh" if they have recent data
                coverage_pct = 100.0 if symbol_count > 0 else 0.0
            else:
                # For symbol-based tables, use ~8000 as baseline (extended universe)
                # S&P 500 + Russell 2000 + others
                coverage_pct = (symbol_count / 8000.0) * 100 if symbol_count > 0 else 0

            return {
                'table': table_name,
                'max_date': max_date,
                'age_hours': age_hours,
                'is_fresh': is_fresh,
                'symbol_count': symbol_count,
                'coverage_pct': min(coverage_pct, 100.0),  # Cap at 100%
                'error': None
            }
    except Exception as e:
        # Reset transaction on error
        try:
            conn.rollback()
        except:
            pass
        return {
            'table': table_name,
            'max_date': None,
            'age_hours': float('inf'),
            'is_fresh': False,
            'symbol_count': 0,
            'coverage_pct': 0.0,
            'error': str(e)
        }

def check_all_tables(conn):
    """Check freshness of all 8 critical tables."""
    results = []
    for table in CRITICAL_TABLES:
        result = get_table_freshness(conn, table)
        results.append(result)
    return results

def is_all_fresh(results):
    """Check if all tables are fresh (<24h) with ≥90% coverage."""
    for r in results:
        if r['error']:
            return False
        if not r['is_fresh']:
            return False
        if r['coverage_pct'] < 90:
            return False
    return True

def print_status(results, iteration):
    """Print current status."""
    et = pytz.timezone('US/Eastern')
    now = datetime.now(et)

    print(f"\n{'='*80}")
    print(f"[FRESHNESS CHECK #{iteration}] {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    print(f"{'='*80}")

    all_fresh = True
    for r in results:
        if r['error']:
            print(f"[ERROR] {r['table']:25} | {r['error']}")
            all_fresh = False
        else:
            status = "[FRESH]" if r['is_fresh'] and r['coverage_pct'] >= 90 else "[STALE]"
            print(f"{status} | {r['table']:25} | Last: {r['max_date']} ({r['age_hours']:.1f}h old) | Symbols: {r['symbol_count']:4} ({r['coverage_pct']:5.1f}%)")
            if not r['is_fresh']:
                all_fresh = False
            if r['coverage_pct'] < 90:
                all_fresh = False

    print(f"{'='*80}")
    if all_fresh:
        print("[SUCCESS] ALL TABLES FRESH WITH >=90% COVERAGE - Pipeline successful!")
    else:
        print("[WAITING] Waiting for fresh data...")

    return all_fresh

def should_stop_monitoring():
    """Check if we should stop monitoring (Monday 5 PM ET or later)."""
    et = pytz.timezone('US/Eastern')
    now = datetime.now(et)

    # Only stop if we reach Monday 5 PM ET or later
    # weekday: 0=Mon, 1=Tue, 2=Wed, 3=Thu, 4=Fri, 5=Sat, 6=Sun

    if now.weekday() == 0:  # It's Monday
        if now.hour >= 17:  # At or after 5 PM
            return True  # Stop: deadline reached
        else:
            return False  # Continue: still Monday morning/afternoon
    elif 1 <= now.weekday() <= 4:  # Tue-Fri: past Monday
        return True  # Stop: past deadline
    else:  # Sat (5) or Sun (6): before Monday
        return False  # Continue: waiting for Monday morning pipeline

def main():
    print("[START] Starting Pipeline Freshness Monitor")
    print("[TARGET] Fresh data from Monday 2 AM ET morning prep pipeline")
    print("[STOP] Data fresh OR Monday 5 PM ET")
    print("[INFO] Monitoring 8 critical tables")

    conn = connect_db()
    if not conn:
        print("[ERROR] Failed to connect to database")
        return 1

    iteration = 0
    start_time = time.time()

    try:
        while True:
            iteration += 1

            # Check all tables
            results = check_all_tables(conn)
            all_fresh = print_status(results, iteration)

            # Stop if all fresh
            if all_fresh:
                print(f"\n[SUCCESS] All tables fresh with >=90% symbol coverage!")
                print(f"[DURATION] Completed in {(time.time() - start_time)/60:.1f} minutes")
                return 0

            # Stop if past Monday 5 PM ET
            if should_stop_monitoring():
                et = pytz.timezone('US/Eastern')
                now = datetime.now(et)
                print(f"\n[DEADLINE] Reached deadline: {now.strftime('%A %I:%M %p %Z')}")
                print(f"[ERROR] Pipeline data not fully fresh by Monday EOD (5 PM ET)")
                return 1

            # Wait 5 minutes before next check (300 seconds)
            print(f"[WAITING] Next check in 5 minutes...")
            time.sleep(300)

    except KeyboardInterrupt:
        print("\n[INTERRUPTED] Monitoring interrupted by user")
        return 1
    finally:
        if conn:
            conn.close()

if __name__ == '__main__':
    sys.exit(main())
