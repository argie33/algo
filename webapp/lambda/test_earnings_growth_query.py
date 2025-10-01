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

def test_earnings_growth_query():
    """Test the earnings growth query."""
    try:
        print(f"Connecting to database at {DB_CONFIG['host']}:{DB_CONFIG['port']}")
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Test the actual query being used in calendar.js
        test_query = """
        SELECT
            symbol,
            symbol as company_name,
            report_date,
            eps_qoq_growth,
            eps_yoy_growth,
            revenue_yoy_growth,
            earnings_surprise_pct,
            fetched_at
          FROM earnings_growth
          ORDER BY symbol ASC, report_date DESC
          LIMIT 25 OFFSET 0
        """

        cur.execute(test_query)
        results = cur.fetchall()

        print(f"Query executed successfully! Got {len(results)} results")
        if results:
            print("Sample result:")
            print(dict(results[0]))
        else:
            print("No data returned - checking earnings_growth table contents")

            cur.execute("SELECT * FROM earnings_growth LIMIT 3")
            sample_data = cur.fetchall()
            print(f"\nActual earnings_growth data:")
            for i, row in enumerate(sample_data, 1):
                print(f"  Row {i}: {dict(row)}")

        cur.close()
        conn.close()

    except Exception as e:
        print(f"❌ Error testing earnings growth query: {e}")
        raise

if __name__ == "__main__":
    test_earnings_growth_query()