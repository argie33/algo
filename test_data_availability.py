#!/usr/bin/env python3
"""
Data availability checker - verifies all required tables have current data.
This detects missing data issues that could cause 404 or empty responses.

Usage:
    python3 test_data_availability.py <DB_HOST> <DB_USER> <DB_PASSWORD> <DB_NAME>

Requirements:
    pip install psycopg2-binary
"""

import sys
from datetime import datetime, date, timedelta
import psycopg2
from psycopg2.extras import RealDictCursor

class DataAvailabilityChecker:
    def __init__(self, host, user, password, database):
        self.conn = psycopg2.connect(
            host=host, user=user, password=password, database=database
        )
        self.cursor = self.conn.cursor(cursor_factory=RealDictCursor)
        self.issues = []

    def check_table_exists(self, table_name: str) -> bool:
        """Check if table exists."""
        self.cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_name = %s
            )
        """, (table_name,))
        return self.cursor.fetchone()[0]

    def check_table_row_count(self, table_name: str) -> int:
        """Get row count for a table."""
        if not self.check_table_exists(table_name):
            self.issues.append(f"TABLE MISSING: {table_name}")
            return 0

        self.cursor.execute(f"SELECT COUNT(*) as cnt FROM {table_name}")
        result = self.cursor.fetchone()
        return result['cnt'] if result else 0

    def check_data_freshness(self, table_name: str, date_column: str) -> dict:
        """Check how fresh data is in a table."""
        if not self.check_table_exists(table_name):
            return {'status': 'MISSING', 'age_days': None}

        try:
            self.cursor.execute(f"""
                SELECT MAX({date_column}) as max_date
                FROM {table_name}
            """)
            result = self.cursor.fetchone()
            if not result or not result['max_date']:
                self.issues.append(f"NO DATA: {table_name} (empty table)")
                return {'status': 'EMPTY', 'age_days': None}

            max_date = result['max_date']
            if isinstance(max_date, datetime):
                max_date = max_date.date()

            age_days = (date.today() - max_date).days
            status = 'FRESH' if age_days <= 1 else 'STALE' if age_days <= 7 else 'CRITICAL'

            if status != 'FRESH':
                self.issues.append(f"STALE DATA: {table_name} ({age_days} days old)")

            return {'status': status, 'age_days': age_days, 'max_date': str(max_date)}
        except Exception as e:
            self.issues.append(f"ERROR checking {table_name}: {e}")
            return {'status': 'ERROR', 'age_days': None}

    def run_checks(self):
        """Run comprehensive data availability checks."""
        print("\n" + "="*80)
        print("DATA AVAILABILITY CHECKER")
        print("="*80 + "\n")

        # Critical tables that must have data
        critical_tables = {
            'price_daily': 'date',
            'buy_sell_daily': 'created_at',
            'stock_scores': 'created_at',
            'trend_template_data': 'date',
            'company_profile': 'created_at',
            'sector_performance': 'date',
            'industry_ranking': 'date',
            'algo_trades': 'created_at',
            'algo_positions': 'created_at',
        }

        print("CRITICAL TABLES")
        print("-" * 80)

        for table, date_col in critical_tables.items():
            freshness = self.check_data_freshness(table, date_col)
            row_count = self.check_table_row_count(table)

            status_display = f"{freshness['status']:8} ({row_count:6} rows)"
            if freshness['age_days'] is not None:
                status_display += f" - {freshness['age_days']} days old"

            print(f"{table:30} {status_display}")

        # Optional tables
        optional_tables = {
            'algo_portfolio_snapshots': 'snapshot_date',
            'algo_notifications': 'created_at',
            'earnings_estimates': 'created_at',
            'value_metrics': 'created_at',
        }

        print("\nOPTIONAL TABLES")
        print("-" * 80)

        for table, date_col in optional_tables.items():
            if not self.check_table_exists(table):
                print(f"{table:30} MISSING (optional)")
                continue

            freshness = self.check_data_freshness(table, date_col)
            row_count = self.check_table_row_count(table)

            status_display = f"{freshness['status']:8} ({row_count:6} rows)"
            if freshness['age_days'] is not None:
                status_display += f" - {freshness['age_days']} days old"

            print(f"{table:30} {status_display}")

        print("\n" + "="*80)
        print("SUMMARY")
        print("="*80 + "\n")

        if self.issues:
            print(f"ISSUES FOUND ({len(self.issues)}):")
            for issue in self.issues:
                print(f"  ✗ {issue}")
        else:
            print("All data tables have current data - system should function normally")

        print("\n")

        # Return success only if no critical issues
        return len(self.issues) == 0

    def close(self):
        self.conn.close()


def main():
    if len(sys.argv) < 5:
        print("Usage: python3 test_data_availability.py <HOST> <USER> <PASSWORD> <DATABASE>")
        print("Example: python3 test_data_availability.py localhost stocks stocks stocks")
        print("\nNote: Requires psycopg2")
        print("  pip install psycopg2-binary")
        sys.exit(1)

    host = sys.argv[1]
    user = sys.argv[2]
    password = sys.argv[3]
    database = sys.argv[4]

    try:
        checker = DataAvailabilityChecker(host, user, password, database)
        success = checker.run_checks()
        checker.close()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"FATAL ERROR: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
