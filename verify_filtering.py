#!/usr/bin/env python3
"""Verify that symbol filtering in loadstockscores.py is working correctly"""

import psycopg2
import os
from dotenv import load_dotenv

load_dotenv()

def get_db_config():
    """Get database configuration"""
    return {
        'host': os.getenv('DB_HOST', 'stocks.cojggi2mkthi.us-east-1.rds.amazonaws.com'),
        'user': os.getenv('DB_USER', 'stocks'),
        'password': os.getenv('DB_PASSWORD', ''),
        'database': os.getenv('DB_NAME', 'stocks')
    }

try:
    config = get_db_config()
    conn = psycopg2.connect(**config)
    cursor = conn.cursor()

    print("=" * 80)
    print("SYMBOL FILTERING VERIFICATION")
    print("=" * 80)

    # Check how many symbols WOULD be excluded by new filters
    exclusion_queries = {
        'Preferred Shares ($ in symbol)': "SELECT COUNT(*) FROM stock_symbols WHERE symbol ILIKE '%$%'",
        'SPACs': "SELECT COUNT(*) FROM stock_symbols WHERE security_name ILIKE '%SPAC%' OR security_name ILIKE '%Special Purpose%' OR security_name ILIKE '%Blank Check%' OR security_name ILIKE '%Acquisition Company%'",
        'ETNs': "SELECT COUNT(*) FROM stock_symbols WHERE security_name ILIKE '%ETN%'",
        'Funds': "SELECT COUNT(*) FROM stock_symbols WHERE security_name ILIKE '%Fund%'",
        'Trusts': "SELECT COUNT(*) FROM stock_symbols WHERE security_name ILIKE '%Trust%'"
    }

    print("\n📊 SYMBOLS THAT WILL BE EXCLUDED:\n")
    for filter_name, query in exclusion_queries.items():
        cursor.execute(query)
        count = cursor.fetchone()[0]
        print(f"  {filter_name:40} {count:5} symbols")

    # Show some examples of excluded symbols
    print("\n📋 EXAMPLE SYMBOLS BEING EXCLUDED:\n")

    print("  Preferred Shares:")
    cursor.execute("SELECT symbol, security_name FROM stock_symbols WHERE symbol ILIKE '%$%' LIMIT 5")
    for row in cursor.fetchall():
        print(f"    - {row[0]:15} {row[1][:50]}")

    print("\n  SPACs:")
    cursor.execute("SELECT symbol, security_name FROM stock_symbols WHERE security_name ILIKE '%SPAC%' LIMIT 5")
    for row in cursor.fetchall():
        print(f"    - {row[0]:15} {row[1][:50]}")

    print("\n  ETNs:")
    cursor.execute("SELECT symbol, security_name FROM stock_symbols WHERE security_name ILIKE '%ETN%' LIMIT 5")
    for row in cursor.fetchall():
        print(f"    - {row[0]:15} {row[1][:50]}")

    # Test the actual filter from loadstockscores.py
    print("\n✅ ACTUAL FILTERED QUERY RESULTS:\n")

    filter_query = """
    SELECT COUNT(DISTINCT s.symbol)
    FROM stock_symbols s
    LEFT JOIN price_daily p ON s.symbol = p.symbol
    LEFT JOIN key_metrics km ON s.symbol = km.ticker
    WHERE s.exchange IN ('NASDAQ', 'New York Stock Exchange', 'American Stock Exchange', 'NYSE Arca', 'BATS Global Markets')
      AND (s.etf = 'N' OR s.etf IS NULL OR s.etf = '')
      AND (s.test_issue != 'Y' OR s.test_issue IS NULL)
      AND (s.financial_status != 'D' OR s.financial_status IS NULL)
      AND s.symbol NOT ILIKE '%$%'
      AND s.security_name NOT ILIKE '%SPAC%'
      AND s.security_name NOT ILIKE '%Special Purpose%'
      AND s.security_name NOT ILIKE '%Blank Check%'
      AND s.security_name NOT ILIKE '%Acquisition Company%'
      AND s.security_name NOT ILIKE '%ETN%'
      AND s.security_name NOT ILIKE '%Fund%'
      AND s.security_name NOT ILIKE '%Trust%'
    """

    cursor.execute(filter_query)
    filtered_count = cursor.fetchone()[0]
    print(f"  Total symbols after filtering: {filtered_count}")

    # Also show unfiltered for comparison
    cursor.execute("""
    SELECT COUNT(DISTINCT s.symbol)
    FROM stock_symbols s
    WHERE s.exchange IN ('NASDAQ', 'New York Stock Exchange', 'American Stock Exchange', 'NYSE Arca', 'BATS Global Markets')
      AND (s.etf = 'N' OR s.etf IS NULL OR s.etf = '')
      AND (s.test_issue != 'Y' OR s.test_issue IS NULL)
      AND (s.financial_status != 'D' OR s.financial_status IS NULL)
    """)
    unfiltered_count = cursor.fetchone()[0]
    print(f"  Total symbols before new filters: {unfiltered_count}")
    print(f"  Symbols excluded by new filters: {unfiltered_count - filtered_count}")

    print("\n" + "=" * 80)
    print("✅ FILTERING VERIFICATION COMPLETE")
    print("=" * 80)

    conn.close()

except psycopg2.Error as e:
    print(f"❌ Database Error: {e}")
except Exception as e:
    print(f"❌ Error: {e}")
