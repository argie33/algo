#!/usr/bin/env python3

import psycopg2
from psycopg2.extras import RealDictCursor

# Database configuration
DB_CONFIG = {
    'host': 'localhost',
    'port': '5432',
    'database': 'stocks',
    'user': 'postgres',
    'password': 'password'
}

def debug_calendar_query():
    """Debug the earnings calendar query."""
    try:
        print(f"Connecting to database at {DB_CONFIG['host']}:{DB_CONFIG['port']}")
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Test the exact query that's failing
        print("Testing the query that's in the earnings route...")

        test_query = """
        SELECT
          er.symbol,
          er.report_date as date,
          er.quarter,
          er.year,
          er.eps_estimate as estimated_eps,
          er.eps_actual as actual_eps,
          NULL as estimated_revenue,
          NULL as actual_revenue,
          s.company_name,
          s.sector,
          s.market_cap
        FROM earnings_reports er
        LEFT JOIN stocks s ON er.symbol = s.symbol
        WHERE er.report_date >= CURRENT_DATE
        ORDER BY er.report_date ASC, er.symbol
        LIMIT 100
        """

        cur.execute(test_query)
        results = cur.fetchall()

        print(f"Query executed successfully! Got {len(results)} results")
        if results:
            print("Sample result:")
            print(dict(results[0]))
        else:
            print("No data returned")

        # Check what's actually in earnings_reports
        cur.execute("SELECT * FROM earnings_reports LIMIT 3")
        sample_data = cur.fetchall()
        print(f"\nActual earnings_reports data:")
        for i, row in enumerate(sample_data, 1):
            print(f"  Row {i}: {dict(row)}")

        cur.close()
        conn.close()

    except Exception as e:
        print(f"❌ Error testing calendar query: {e}")
        raise

if __name__ == "__main__":
    debug_calendar_query()