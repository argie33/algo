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

def test_earnings_metrics_query():
    """Test the earnings metrics query."""
    try:
        print(f"Connecting to database at {DB_CONFIG['host']}:{DB_CONFIG['port']}")
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor(cursor_factory=RealDictCursor)

        # Test the actual query being used in calendar.js
        test_query = """
        SELECT
            symbol,
            symbol as company_name,
            quarter as report_date,
            eps_actual,
            eps_estimate,
            surprise_percent as eps_surprise_last_q,
            CASE
              WHEN eps_actual IS NOT NULL AND eps_estimate IS NOT NULL
              THEN ((eps_actual - eps_estimate) / NULLIF(eps_estimate, 0)) * 100
              ELSE NULL
            END as eps_growth_1q,
            0 as eps_growth_2q,
            0 as eps_growth_4q,
            0 as eps_growth_8q,
            0 as eps_acceleration_qtrs,
            0 as eps_estimate_revision_1m,
            0 as eps_estimate_revision_3m,
            0 as eps_estimate_revision_6m,
            0 as annual_eps_growth_1y,
            0 as annual_eps_growth_3y,
            0 as annual_eps_growth_5y,
            0 as consecutive_eps_growth_years,
            0 as eps_estimated_change_this_year
          FROM earnings_history
          ORDER BY symbol ASC, quarter DESC
          LIMIT 25 OFFSET 0
        """

        cur.execute(test_query)
        results = cur.fetchall()

        print(f"Query executed successfully! Got {len(results)} results")
        if results:
            print("Sample result:")
            print(dict(results[0]))
        else:
            print("No data returned - checking earnings_history table contents")

            cur.execute("SELECT * FROM earnings_history LIMIT 3")
            sample_data = cur.fetchall()
            print(f"\nActual earnings_history data:")
            for i, row in enumerate(sample_data, 1):
                print(f"  Row {i}: {dict(row)}")

        cur.close()
        conn.close()

    except Exception as e:
        print(f"❌ Error testing earnings metrics query: {e}")
        raise

if __name__ == "__main__":
    test_earnings_metrics_query()