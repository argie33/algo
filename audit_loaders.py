#!/usr/bin/env python3
"""Audit all loaders for silent failures and data consistency issues"""
import os
import psycopg2
import subprocess
from datetime import datetime, timedelta

db_config = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "user": os.getenv("DB_USER", "stocks"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_NAME", "stocks")
}

print("\n" + "=" * 90)
print("LOADER AUDIT REPORT - SILENT FAILURES AND DATA CONSISTENCY")
print("=" * 90)

try:
    conn = psycopg2.connect(**db_config)
    cur = conn.cursor()

    # Critical earnings tables status
    print("\n📊 CRITICAL EARNINGS DATA TABLES")
    print("-" * 90)

    critical_tables = {
        "earnings_estimate_trends": "eps_trend data from yfinance",
        "earnings_estimate_revisions": "eps_revisions data from yfinance",
        "earnings_history": "Actual earnings history",
        "earnings_estimates": "Earnings estimates (analyst forecasts)"
    }

    for table, description in critical_tables.items():
        try:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            count = cur.fetchone()[0]

            # Get latest snapshot date
            cur.execute(f"""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = '{table}' AND column_name IN ('snapshot_date', 'quarter', 'created_at')
                LIMIT 1
            """)
            result = cur.fetchone()

            if result:
                col_name = result[0]
                cur.execute(f"SELECT MAX({col_name}) FROM {table}")
                latest = cur.fetchone()[0]
                if latest and isinstance(latest, str):
                    latest = str(latest)[:10]
                else:
                    latest = str(latest)[:10] if latest else "NULL"
                status = "✓" if count > 0 else "🔴 EMPTY"
            else:
                status = "✓" if count > 0 else "🔴 EMPTY"
                latest = "N/A"

            print(f"{status} {table}: {count:,} records | Latest: {latest}")
            print(f"   → {description}")

        except psycopg2.Error as e:
            print(f"✗ {table}: {str(e)[:80]}")

    # Check symbol coverage
    print("\n🎯 SYMBOL COVERAGE")
    print("-" * 90)

    cur.execute("SELECT COUNT(*) FROM stock_symbols WHERE etf = 'N'")
    total_stocks = cur.fetchone()[0]

    cur.execute("SELECT COUNT(DISTINCT symbol) FROM earnings_history")
    stocks_with_earnings_history = cur.fetchone()[0]

    cur.execute("SELECT COUNT(DISTINCT symbol) FROM earnings_estimates")
    stocks_with_earnings_estimates = cur.fetchone()[0]

    cur.execute("SELECT COUNT(DISTINCT symbol) FROM earnings_estimate_trends")
    stocks_with_estimate_trends = cur.fetchone()[0]

    cur.execute("SELECT COUNT(DISTINCT symbol) FROM earnings_estimate_revisions")
    stocks_with_estimate_revisions = cur.fetchone()[0]

    print(f"Total stocks in database: {total_stocks}")
    print(f"Stocks with earnings history: {stocks_with_earnings_history} ({100*stocks_with_earnings_history/total_stocks:.1f}%)")
    print(f"Stocks with earnings estimates: {stocks_with_earnings_estimates} ({100*stocks_with_earnings_estimates/total_stocks:.1f}%)")
    print(f"Stocks with estimate trends: {stocks_with_estimate_trends} ({100*stocks_with_estimate_trends/total_stocks:.1f}%)")
    print(f"Stocks with estimate revisions: {stocks_with_estimate_revisions} ({100*stocks_with_estimate_revisions/total_stocks:.1f}%)")

    # Check for obviously broken data
    print("\n🚨 DATA INTEGRITY ISSUES")
    print("-" * 90)

    # Check for duplicate earnings records
    cur.execute("""
        SELECT symbol, quarter, COUNT(*) as dupes
        FROM earnings_history
        GROUP BY symbol, quarter
        HAVING COUNT(*) > 1
        LIMIT 5
    """)
    dupes = cur.fetchall()
    if dupes:
        print(f"🔴 {len(dupes)} duplicate earnings records found")
        for row in dupes:
            print(f"   {row[0]} - {row[1]}: {row[2]} copies")
    else:
        print("✓ No duplicate earnings records")

    # Check for null values in critical fields
    cur.execute("""
        SELECT COUNT(*) FROM earnings_history
        WHERE eps_actual IS NULL AND eps_estimate IS NULL
    """)
    null_count = cur.fetchone()[0]
    if null_count > 0:
        print(f"🟡 {null_count} earnings records with all null values")
    else:
        print("✓ No null earnings records")

    # Check database connection consistency
    print("\n🔗 DATABASE CONNECTION")
    print("-" * 90)
    cur.execute("SELECT version()")
    version = cur.fetchone()[0]
    print(f"✓ Connected to: {version.split(',')[0]}")

    print("\n" + "=" * 90)
    print("END AUDIT REPORT")
    print("=" * 90 + "\n")

    conn.close()

except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
