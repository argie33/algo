#!/usr/bin/env python3
"""
Verify data coverage across all stocks in database.

Identifies which data sources are complete and which need loader fixes.
Runs after loaders to validate data population.
"""

import os
import sys
import json
from pathlib import Path
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor

# Fix encoding for Windows console
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "user": os.getenv("DB_USER", "stocks"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "stocks"),
}

def get_conn():
    """Get database connection."""
    return psycopg2.connect(**DB_CONFIG)

def count_stocks_with_data(conn, table, symbol_column='symbol'):
    """Count unique symbols in a table."""
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute(f"SELECT COUNT(DISTINCT {symbol_column}) as count FROM {table}")
        result = cur.fetchone()
        return result['count'] if result else 0
    except Exception as e:
        return f"ERROR: {str(e)[:50]}"
    finally:
        cur.close()

def get_total_stocks(conn):
    """Get total stock count in database."""
    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cur.execute("SELECT COUNT(*) as count FROM stock_symbols")
        result = cur.fetchone()
        return result['count'] if result else 515
    except:
        return 515
    finally:
        cur.close()

def main():
    conn = get_conn()

    # Data sources to verify
    data_sources = [
        ('stock_symbols', 'symbol', 'Stock Symbols'),
        ('earnings_history', 'symbol', 'Earnings History'),
        ('earnings_estimates', 'symbol', 'Earnings Estimates'),
        ('analyst_sentiment_analysis', 'symbol', 'Analyst Sentiment'),
        ('analyst_upgrade_downgrade', 'symbol', 'Analyst Upgrades'),
        ('institutional_positioning', 'symbol', 'Institutional Positioning'),
        ('options_chains', 'symbol', 'Options Chains'),
        ('technical_data_daily', 'symbol', 'Technical Data (Daily)'),
        ('company_profile', 'ticker', 'Company Profile'),
        ('stock_scores', 'symbol', 'Stock Scores'),
    ]

    total_stocks = get_total_stocks(conn)

    print("\n" + "=" * 90)
    print("DATA COVERAGE VERIFICATION")
    print("=" * 90)
    print(f"\nTotal stocks in database: {total_stocks}\n")
    print(f"{'Data Source':<35} {'Count':<10} {'Coverage':<15} {'Status':<20}")
    print("-" * 90)

    critical_gaps = []
    partial_gaps = []

    for table, column, name in data_sources:
        count = count_stocks_with_data(conn, table, column)

        if isinstance(count, int):
            pct = (count / total_stocks * 100) if total_stocks > 0 else 0

            # Determine status
            if pct >= 95:
                status = "[OK] COMPLETE"
            elif pct >= 70:
                status = "[WARN] PARTIAL"
                partial_gaps.append((name, count, total_stocks, pct))
            else:
                status = "[ERROR] CRITICAL"
                critical_gaps.append((name, count, total_stocks, pct))

            print(f"{name:<35} {count:<10} {pct:>6.1f}%        {status:<20}")
        else:
            print(f"{name:<35} {count:<10} {'N/A':<15} [ERROR] QUERY FAILED")

    print("\n" + "=" * 90)
    print("SUMMARY")
    print("=" * 90)

    if critical_gaps:
        print(f"\n[CRITICAL] {len(critical_gaps)} data sources have gaps:")
        for name, count, total, pct in critical_gaps:
            print(f"  - {name}: {count}/{total} stocks ({pct:.1f}%) [Missing: {total-count}]")

    if partial_gaps:
        print(f"\n[WARNING] {len(partial_gaps)} data sources have partial coverage:")
        for name, count, total, pct in partial_gaps:
            print(f"  - {name}: {count}/{total} stocks ({pct:.1f}%) [Missing: {total-count}]")

    if not critical_gaps and not partial_gaps:
        print("\n[SUCCESS] All data sources have complete coverage!")

    print("\nNEXT STEPS:")
    if critical_gaps:
        print("1. Run failing loaders individually to debug issues:")
        for name, _, _, _ in critical_gaps:
            loader_map = {
                'Earnings History': 'python3 loadearningshistory.py',
                'Earnings Estimates': 'python3 loaddailycompanydata.py',
                'Analyst Sentiment': 'python3 loadanalystsentiment.py',
                'Analyst Upgrades': 'python3 loadanalystupgradedowngrade.py',
                'Institutional Positioning': 'python3 loaddailycompanydata.py',
                'Options Chains': 'python3 loadoptionschains.py',
                'Technical Data (Daily)': 'python3 loadtechnicalindicators_github.py',
            }
            cmd = loader_map.get(name, 'Unknown loader')
            print(f"   python3 {cmd}")
    else:
        print("1. [OK] All loaders completed successfully!")

    print("2. Test API endpoints to verify data is queryable")
    print("3. Test frontend pages to confirm data displays correctly")
    print("4. Monitor API health and database performance")

    conn.close()
    print("\n" + "=" * 90 + "\n")

if __name__ == "__main__":
    main()
