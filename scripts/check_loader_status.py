#!/usr/bin/env python3
"""Check recent loader executions and status."""
import os
import sys
from datetime import datetime, timedelta
import psycopg2
from config.credential_helper import get_db_config

def main():
    try:
        config = get_db_config()
        conn = psycopg2.connect(
            host=config['host'],
            port=config['port'],
            database=config['database'],
            user=config['user'],
            password=config['password'],
            sslmode=config.get('sslmode', 'disable')
        )
        cursor = conn.cursor()

        # Check recent loader status
        query = """
        SELECT
            table_name,
            latest_date,
            status,
            row_count,
            age_days,
            error_message,
            last_updated
        FROM data_loader_status
        ORDER BY last_updated DESC
        LIMIT 50
        """

        cursor.execute(query)
        results = cursor.fetchall()

        print("=" * 120)
        print("DATA LOADER STATUS")
        print("=" * 120)
        print(f"{'Table':<40} {'Latest Date':<12} {'Status':<10} {'Rows':<12} {'Age (days)':<12} {'Error':<30}")
        print("-" * 120)

        today = datetime.now().date()
        today_loaders = []

        for row in results:
            table, latest_date, status, row_count, age_days, error, last_updated = row
            if latest_date and latest_date == today:
                today_loaders.append(table)
            error_str = (error[:27] + "...") if error else ""
            date_str = str(latest_date) if latest_date else "N/A"
            age_str = str(age_days) if age_days is not None else "N/A"
            row_str = str(row_count) if row_count is not None else "N/A"
            status_str = str(status) if status is not None else "N/A"
            print(f"{table:<40} {date_str:<12} {status_str:<10} {row_str:<12} {age_str:<12} {error_str:<30}")

        print("\n" + "=" * 100)
        print(f"Today is: {today} ({today.strftime('%A')})")
        print(f"Loaders that ran TODAY: {len(today_loaders)}")
        if today_loaders:
            for loader in today_loaders:
                print(f"  - {loader}")
        else:
            print("  (None - expected if today is a weekend or holiday)")

        cursor.close()
        conn.close()

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
