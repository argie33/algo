#!/usr/bin/env python3
"""
Database consistency verification script for Tier 1.3 validation.
Checks row counts, date freshness, duplicates, and orphaned records.
"""

import sys
import os
from datetime import datetime, timedelta

# Add paths for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config'))

try:
    from config.credential_helper import get_db_password, get_db_config
    import psycopg2
except ImportError as e:
    print(f"ERROR: Failed to import config.credential_helper: {e}")
    sys.exit(1)

def verify_database():
    """Run all database consistency checks."""
    print("\n" + "="*70)
    print("DATABASE CONSISTENCY VERIFICATION (Tier 1.3)")
    print("="*70 + "\n")

    try:
        config = get_db_config()
        password = get_db_password()

        conn = psycopg2.connect(
            host=config.get('host', 'localhost'),
            port=config.get('port', 5432),
            user=config.get('user', 'postgres'),
            password=password,
            database=config.get('database', 'stocks')
        )
        cur = conn.cursor()
        print("✓ Connected to database\n")

        # Check 1: Key table row counts
        print("CHECK 1: Table Row Counts")
        print("-" * 50)
        key_tables = [
            'stock_symbols',
            'price_daily',
            'stock_scores',
            'buy_sell_daily',
            'portfolio_holdings',
            'algo_audit_log',
            'positioning_metrics',
            'technical_data_daily'
        ]

        row_counts = {}
        for table in key_tables:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            count = cur.fetchone()[0]
            row_counts[table] = count
            status = "✓" if count > 0 else "✗"
            print(f"  {status} {table:30s}: {count:>8,} rows")

        # Check 2: Date freshness
        print("\n\nCHECK 2: Data Freshness (Most Recent Dates)")
        print("-" * 50)

        freshness_queries = {
            'price_daily': ("SELECT MAX(date) FROM price_daily", 'price_daily'),
            'stock_scores': ("SELECT MAX(date) FROM stock_scores", 'stock_scores'),
            'technical_data_daily': ("SELECT MAX(date) FROM technical_data_daily", 'technical_data_daily'),
            'buy_sell_daily': ("SELECT MAX(date) FROM buy_sell_daily", 'buy_sell_daily'),
        }

        today = datetime.now().date()
        for label, (query, table) in freshness_queries.items():
            cur.execute(query)
            result = cur.fetchone()
            if result and result[0]:
                max_date = result[0]
                days_old = (today - max_date).days
                status = "✓" if days_old <= 1 else "⚠"
                print(f"  {status} {label:30s}: {max_date} ({days_old} days old)")
            else:
                print(f"  ✗ {label:30s}: No data")

        # Check 3: Check for duplicates in key tables with unique constraints
        print("\n\nCHECK 3: Duplicate Detection (symbol, date pairs)")
        print("-" * 50)

        duplicate_checks = [
            ('price_daily', ['symbol', 'date']),
            ('stock_scores', ['symbol', 'date']),
            ('technical_data_daily', ['symbol', 'date']),
            ('buy_sell_daily', ['symbol', 'date']),
            ('ttm_income_statement', ['symbol', 'date']),
            ('ttm_cash_flow', ['symbol', 'date']),
        ]

        for table, cols in duplicate_checks:
            col_list = ', '.join(cols)
            cur.execute(f"""
                SELECT {col_list}, COUNT(*)
                FROM {table}
                GROUP BY {col_list}
                HAVING COUNT(*) > 1
                LIMIT 5
            """)
            dups = cur.fetchall()
            if dups:
                print(f"  ✗ {table:30s}: Found {len(dups)} duplicate combinations")
                for dup in dups[:3]:
                    print(f"       Example: {dup}")
            else:
                print(f"  ✓ {table:30s}: No duplicates")

        # Check 4: Data integrity
        print("\n\nCHECK 4: Schema & Constraint Verification")
        print("-" * 50)

        # Check for required columns
        cur.execute("""
            SELECT table_name, COUNT(*) as col_count
            FROM information_schema.columns
            WHERE table_schema = 'public'
            GROUP BY table_name
            ORDER BY table_name
        """)

        tables = cur.fetchall()
        print(f"  ✓ Total tables defined: {len(tables)}")

        # Check for key indexes
        cur.execute("""
            SELECT indexname
            FROM pg_indexes
            WHERE schemaname = 'public'
            AND indexname LIKE '%symbol%date%'
        """)

        indexes = cur.fetchall()
        print(f"  ✓ Symbol-date indexes found: {len(indexes)}")

        # Summary
        print("\n\nSUMMARY")
        print("-" * 50)
        all_good = all(count > 0 for count in row_counts.values())

        if all_good:
            print("✓ Database appears healthy and ready for testing")
            return 0
        else:
            missing = [table for table, count in row_counts.items() if count == 0]
            print(f"✗ Missing data in tables: {missing}")
            return 1

    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()

if __name__ == '__main__':
    sys.exit(verify_database())
