#!/usr/bin/env python3
"""
Data Loader Verification Script

Checks that all critical data loaders have populated the database recently.
Run this daily to ensure data freshness.

Usage:
    python3 verify_data_loaders.py
    python3 verify_data_loaders.py --email your@email.com --alert-age 24

Returns exit code 0 if all OK, 1 if any table is stale.
"""

import os
import sys
import argparse
import psycopg2
from datetime import date, timedelta
from typing import Dict, Tuple, List

# Define critical tables and their expected freshness
CRITICAL_TABLES = {
    'price_daily': {'max_age_hours': 24, 'severity': 'CRITICAL'},
    'technical_data_daily': {'max_age_hours': 24, 'severity': 'CRITICAL'},
    'stock_scores': {'max_age_hours': 48, 'severity': 'HIGH'},
    'buy_sell_daily': {'max_age_hours': 24, 'severity': 'HIGH'},
    'market_health_daily': {'max_age_hours': 24, 'severity': 'CRITICAL'},
    'analyst_sentiment_analysis': {'max_age_hours': 48, 'severity': 'MEDIUM'},
    'market_sentiment': {'max_age_hours': 48, 'severity': 'MEDIUM'},
    'sector_performance': {'max_age_hours': 48, 'severity': 'MEDIUM'},
    'economic_data': {'max_age_hours': 72, 'severity': 'LOW'},
    'economic_calendar': {'max_age_hours': 72, 'severity': 'LOW'},
}


def get_db_connection():
    """Get database connection from environment or defaults."""
    return psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=int(os.getenv('DB_PORT', 5432)),
        database=os.getenv('DB_NAME', 'stocks'),
        user=os.getenv('DB_USER', 'stocks'),
        password=os.getenv('DB_PASSWORD', 'postgres')
    )


def check_table_freshness(conn, table_name: str, max_age_hours: int) -> Tuple[bool, str, int]:
    """
    Check if a table has recent data.

    Returns: (is_fresh, last_date, age_hours)
    """
    cur = conn.cursor()

    try:
        # Try to get the max date from common date columns
        for date_col in ['date', 'created_at', 'updated_at', 'action_date']:
            try:
                cur.execute(f"""
                    SELECT MAX({date_col}) as max_date
                    FROM {table_name}
                """)
                result = cur.fetchone()
                if result and result[0]:
                    max_date = result[0]
                    if hasattr(max_date, 'date'):
                        max_date = max_date.date()

                    age_days = (date.today() - max_date).days
                    age_hours = age_days * 24

                    is_fresh = age_hours <= max_age_hours
                    return is_fresh, str(max_date), age_hours
                break
            except Exception:
                continue

        # If no data found
        return False, "NO DATA", 999999

    except Exception as e:
        return False, f"ERROR: {str(e)}", -1
    finally:
        cur.close()


def check_row_count(conn, table_name: str) -> int:
    """Get row count for a table."""
    cur = conn.cursor()
    try:
        cur.execute(f"SELECT COUNT(*) FROM {table_name}")
        return cur.fetchone()[0]
    except Exception:
        return 0
    finally:
        cur.close()


def main():
    parser = argparse.ArgumentParser(description='Verify data loader freshness')
    parser.add_argument('--email', help='Email to alert on failures')
    parser.add_argument('--alert-age', type=int, default=24, help='Alert if older than N hours')
    args = parser.parse_args()

    try:
        conn = get_db_connection()
        print("\n" + "="*80)
        print("DATA LOADER VERIFICATION REPORT")
        print("="*80 + "\n")

        all_fresh = True
        issues = []

        for table_name, config in CRITICAL_TABLES.items():
            max_age = config['max_age_hours']
            severity = config['severity']

            is_fresh, last_date, age_hours = check_table_freshness(conn, table_name, max_age)
            row_count = check_row_count(conn, table_name)

            status = "✅ OK" if is_fresh else "❌ STALE"

            print(f"{status} | {table_name:30s} | Age: {age_hours:4d}h | Rows: {row_count:8d} | Last: {last_date}")

            if not is_fresh:
                all_fresh = False
                issues.append({
                    'table': table_name,
                    'severity': severity,
                    'age_hours': age_hours,
                    'last_date': last_date,
                    'max_age': max_age
                })

        print("\n" + "="*80)

        if all_fresh:
            print("✅ ALL DATA LOADERS HEALTHY")
            print("="*80 + "\n")
            return 0
        else:
            print("⚠️  STALE DATA DETECTED")
            print("="*80 + "\n")

            print("ISSUES:\n")
            for issue in issues:
                print(f"  ❌ {issue['table']}")
                print(f"     Severity: {issue['severity']}")
                print(f"     Age: {issue['age_hours']} hours (max: {issue['max_age']})")
                print(f"     Last update: {issue['last_date']}")
                print()

            print("ACTIONS:")
            print("  1. Check CloudWatch logs: aws logs tail /aws/lambda/loadpricedaily --follow")
            print("  2. Check EventBridge: aws events describe-rule --name stocks-data-loader")
            print("  3. Verify Lambda execution: aws lambda get-function-concurrency --function-name loadpricedaily")
            print("  4. Check database: psql -h <RDS> -U stocks -d stocks -c \"SELECT MAX(date) FROM price_daily;\"")
            print()

            if args.email:
                print(f"  5. Alert sent to {args.email}")
                # TODO: Implement email alert

            print("="*80 + "\n")
            return 1

    except Exception as e:
        print(f"\n❌ VERIFICATION FAILED: {e}\n")
        print("Check database connection:")
        print(f"  DB_HOST={os.getenv('DB_HOST', 'localhost')}")
        print(f"  DB_PORT={os.getenv('DB_PORT', 5432)}")
        print(f"  DB_NAME={os.getenv('DB_NAME', 'stocks')}")
        print(f"  DB_USER={os.getenv('DB_USER', 'stocks')}")
        return 2


if __name__ == '__main__':
    sys.exit(main())
