#!/usr/bin/env python3
"""
Audit what data is actually in the database vs what's needed
"""
import psycopg2
import os
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

# Load env
env_file = Path(__file__).parent / '.env.local'
if env_file.exists():
    load_dotenv(env_file)

# Connect to database
try:
    conn = psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        user=os.getenv('DB_USER', 'postgres'),
        password=os.getenv('DB_PASSWORD'),
        database=os.getenv('DB_NAME', 'stocks'),
        port=os.getenv('DB_PORT', 5432)
    )
    cur = conn.cursor()

    print("=" * 70)
    print("DATA COMPLETENESS AUDIT")
    print("=" * 70)
    print()

    # Check total symbols
    cur.execute("SELECT COUNT(*) FROM stock_symbols WHERE is_active = TRUE")
    total_symbols = cur.fetchone()[0]
    print(f"OK Total active symbols: {total_symbols}")
    print()

    # Check critical data tables
    critical_tables = [
        ('stock_symbols', 'symbol'),
        ('company_profile', 'ticker'),
        ('earnings_calendar', 'symbol'),
        ('earnings_history', 'symbol'),
        ('earnings_estimates', 'symbol'),
        ('analyst_sentiment', 'symbol'),
        ('price_daily', 'symbol'),
        ('buy_sell_signals', 'symbol'),
        ('stock_scores', 'symbol'),
        ('technical_data_daily', 'symbol'),
    ]

    print("[TABLES] TABLE POPULATION STATUS:")
    print("-" * 70)

    for table, symbol_col in critical_tables:
        # Check if table exists
        cur.execute(f"""
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = '{table}'
            )
        """)

        if not cur.fetchone()[0]:
            print(f"NO  {table.ljust(30)} - TABLE DOES NOT EXIST")
            continue

        # Check row count
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        count = cur.fetchone()[0]

        # Check coverage (% of total symbols with data)
        if table != 'stock_symbols':
            cur.execute(f"""
                SELECT COUNT(DISTINCT {symbol_col})
                FROM {table}
            """)
            unique_symbols = cur.fetchone()[0]
            coverage = (unique_symbols / total_symbols * 100) if total_symbols > 0 else 0

            status = "OK" if coverage > 90 else "LOW" if coverage > 50 else "EMPTY"
            print(f"{status} {table.ljust(30)} {count:>12,} rows | {coverage:>5.1f}% coverage ({unique_symbols:,} symbols)")
        else:
            print(f"OK {table.ljust(30)} {count:>12,} rows")

    print()
    print("=" * 70)
    print("CRITICAL GAPS TO ADDRESS:")
    print("-" * 70)

    # Check earnings_calendar specifically
    cur.execute("SELECT COUNT(*) FROM earnings_calendar")
    earnings_count = cur.fetchone()[0]

    # Check analyst sentiment
    cur.execute("SELECT COUNT(*) FROM analyst_sentiment")
    sentiment_count = cur.fetchone()[0]

    gaps = []
    if earnings_count < 100:
        gaps.append(f"MISSING: earnings_calendar: Only {earnings_count} rows (need ~10K+ for meaningful blackout)")
    else:
        gaps.append(f"OK: earnings_calendar: {earnings_count} rows")

    if sentiment_count < 100:
        gaps.append(f"MISSING: analyst_sentiment: Only {sentiment_count} rows (need ~5K+ for sentiment signals)")
    else:
        gaps.append(f"OK: analyst_sentiment: {sentiment_count} rows")

    for gap in gaps:
        print(gap)

    print()
    print("=" * 70)
    print("RECOMMENDED ACTIONS:")
    print("-" * 70)

    if earnings_count < 100:
        print("""
1. RUN: python3 loaders/load_earnings_calendar.py
   - Fetches 6-12 months of earnings dates
   - Required for: Earnings blackout enforcement
   - Estimated time: 2-3 minutes for 10K+ symbols
        """)

    if sentiment_count < 100:
        print("""
2. RUN: python3 loaders/loadanalystsentiment.py
   - Fetches analyst sentiment ratings
   - Required for: Sentiment-based signals
   - Estimated time: 5-10 minutes for 10K+ symbols
        """)

    print("""
3. VERIFY loaders are in Terraform ECS task:
   - Check: terraform/modules/loaders/main.tf
   - Ensure: load_earnings_calendar.py and loadanalystsentiment.py in LOADER_FILE_MAP
   - These should run daily in production
    """)

    print("=" * 70)

    conn.close()

except Exception as e:
    print(f"ERROR: Database error: {e}")
    print("\nMake sure PostgreSQL is running and .env.local is configured")
