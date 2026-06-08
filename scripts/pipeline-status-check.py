#!/usr/bin/env python3
"""
Quick pipeline status check - reports freshness of 8 critical tables.
Returns exit code 0 if all fresh, 1 if any stale.
"""

import os
import sys
from datetime import datetime
import psycopg2
from psycopg2.extras import RealDictCursor
import pytz

if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

CRITICAL_TABLES = [
    'price_daily',
    'technical_data_daily',
    'buy_sell_daily',
    'signal_quality_scores',
    'swing_trader_scores',
    'market_health_daily',
    'trend_template_data',
    'sector_ranking'
]

def get_db_config():
    """Get database configuration from environment."""
    return {
        'host': os.getenv('DB_HOST', 'localhost'),
        'port': int(os.getenv('DB_PORT', 5432)),
        'database': os.getenv('DB_NAME', 'algo'),
        'user': os.getenv('DB_USER', 'postgres'),
        'password': os.getenv('DB_PASSWORD', ''),
    }

def check_table(conn, table_name):
    """Check table freshness and symbol coverage."""
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if table_name == 'sector_ranking':
                cur.execute(f"SELECT MAX(date)::TEXT as max_date, COUNT(DISTINCT sector_name) as count FROM {table_name}")
            elif table_name == 'market_health_daily':
                cur.execute(f"SELECT MAX(date)::TEXT as max_date, COUNT(*) as count FROM {table_name}")
            else:
                cur.execute(f"SELECT MAX(date)::TEXT as max_date, COUNT(DISTINCT symbol) as count FROM {table_name}")

            result = cur.fetchone()
            if not result or not result['max_date']:
                return {'table': table_name, 'status': 'NO_DATA', 'max_date': None, 'age_h': float('inf')}

            max_date = datetime.strptime(result['max_date'], '%Y-%m-%d').date()
            now = datetime.now().date()
            age_h = (now - max_date).days * 24
            is_fresh = age_h < 24

            return {
                'table': table_name,
                'status': 'FRESH' if is_fresh else 'STALE',
                'max_date': str(max_date),
                'age_h': age_h,
                'count': result['count']
            }
    except Exception as e:
        return {'table': table_name, 'status': 'ERROR', 'error': str(e)}

def main():
    """Run status check."""
    et = pytz.timezone('US/Eastern')
    now = datetime.now(et)

    print(f"\n[CHECK] {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")

    try:
        config = get_db_config()
        conn = psycopg2.connect(**config)
    except Exception as e:
        print(f"[ERROR] DB connection failed: {e}")
        return 1

    results = []
    all_fresh = True
    fresh_count = 0

    for table in CRITICAL_TABLES:
        result = check_table(conn, table)
        results.append(result)

        if result['status'] == 'FRESH':
            print(f"[FRESH] {result['table']:25} | {result['max_date']} ({result['age_h']:.0f}h old) | {result['count']} symbols")
            fresh_count += 1
        else:
            status_str = result['status'] if result['status'] != 'NO_DATA' else 'EMPTY'
            age_str = f"{result.get('age_h', '?'):.0f}h old" if result.get('age_h') != float('inf') else 'no data'
            print(f"[{status_str}] {result['table']:25} | {result.get('max_date', 'N/A'):10} ({age_str})")
            all_fresh = False

    conn.close()

    print(f"\n[SUMMARY] {fresh_count}/8 tables FRESH")

    if all_fresh:
        print("[SUCCESS] All tables have fresh data - pipeline complete!")
        return 0
    else:
        print("[WAITING] Some tables still stale - pipeline not yet complete")
        return 1


if __name__ == '__main__':
    sys.exit(main())
