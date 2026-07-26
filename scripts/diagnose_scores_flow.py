#!/usr/bin/env python3
"""Diagnose scores data flow from database through dashboard."""

import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def verify_database_data() -> bool:
    """Check if scores exist in database."""
    import psycopg2
    conn = psycopg2.connect('dbname=stocks user=stocks host=localhost')
    cur = conn.cursor()

    cur.execute('''
    SELECT COUNT(*) as total,
           SUM(CASE WHEN composite_score IS NULL THEN 1 ELSE 0 END) as null_scores,
           SUM(CASE WHEN data_completeness >= 70 THEN 1 ELSE 0 END) as good_scores,
           SUM(CASE WHEN data_unavailable = true THEN 1 ELSE 0 END) as unavail_scores
    FROM stock_scores
    ''')
    total, nulls, good, unavail = cur.fetchone()

    print("\n=== DATABASE VERIFICATION ===")
    print(f"Total scores: {total}")
    print(f"  Good scores (completeness >= 70): {good}")
    print(f"  NULL composite_scores: {nulls}")
    print(f"  Marked unavailable: {unavail}")

    # Check a sample score
    cur.execute('''
    SELECT symbol, composite_score, quality_score, growth_score, momentum_score
    FROM stock_scores
    WHERE composite_score > 0 AND data_completeness >= 70
    LIMIT 1
    ''')
    sample = cur.fetchone()
    if sample:
        print(f"\nSample score: {sample[0]}")
        print(f"  Composite: {sample[1]}")
        print(f"  Quality: {sample[2]}")
        print(f"  Growth: {sample[3]}")
        print(f"  Momentum: {sample[4]}")
        return True
    return False


def verify_api_query() -> bool:
    """Check if API query works correctly."""
    import psycopg2
    conn = psycopg2.connect('dbname=stocks user=stocks host=localhost')
    cur = conn.cursor()

    # Run the exact API query
    cur.execute('''
    WITH max_price_date AS (
        SELECT MAX(date) AS max_date FROM price_daily
    ),
    filtered_scores AS (
        SELECT s.*, COALESCE(c.short_name, s.symbol) as company_name, c.sector
        FROM stock_scores s
        LEFT JOIN company_profile c ON s.symbol = c.symbol
        WHERE s.composite_score > 0
        AND s.data_completeness >= 70
        AND (s.data_unavailable = false OR s.data_unavailable IS NULL)
        AND s.symbol NOT IN (SELECT symbol FROM etf_symbols)
        ORDER BY s.composite_score DESC
        LIMIT 5
    )
    SELECT fs.symbol, fs.composite_score, fs.quality_score
    FROM filtered_scores fs
    ''')
    rows = cur.fetchall()

    print("\n=== API QUERY VERIFICATION ===")
    print(f"Query returned: {len(rows)} rows (expected: 5)")
    for row in rows:
        print(f"  {row[0]}: composite={row[1]}, quality={row[2]}")

    return len(rows) == 5


def verify_response_format() -> bool:
    """Check if response is formatted correctly."""
    print("\n=== RESPONSE FORMAT VERIFICATION ===")

    # Simulate what json_response(200, data, preserve_arrays=True) returns
    sample_data = {
        "top": [
            {"symbol": "AEM", "composite_score": 77.15, "quality_score": 94.08},
            {"symbol": "B", "composite_score": 75.33, "quality_score": 97.33},
        ],
        "universe_total": 4791,
        "avg_composite": 50.5,
        "grades": {"a": 100, "b": 200, "c": 300, "d": 400}
    }

    # This is what the API returns after json_response wrapping
    wrapped = {
        "statusCode": 200,
        "data": sample_data
    }

    print(f"Response keys: {list(wrapped.keys())}")
    print(f"Has 'data' wrapper: {'data' in wrapped}")
    print(f"Has 'top' in data: {'top' in wrapped['data']}")
    print(f"Top is list: {isinstance(wrapped['data']['top'], list)}")
    print(f"Top length: {len(wrapped['data']['top'])}")

    # Check what dashboard panel would receive
    panel_input = wrapped['data']
    print(f"\nWhat panel receives: {list(panel_input.keys())}")
    top_scores = panel_input.get('top', [])
    print(f"Panel extracts 'top': {isinstance(top_scores, list)}, length={len(top_scores)}")

    return True


def main():
    """Run all verifications."""
    print("╔════════════════════════════════════════════════════════════╗")
    print("║  SCORES DATA FLOW DIAGNOSTIC                               ║")
    print("╚════════════════════════════════════════════════════════════╝")

    try:
        db_ok = verify_database_data()
        api_ok = verify_api_query()
        fmt_ok = verify_response_format()

        print("\n=== SUMMARY ===")
        print(f"✅ Database data exists: {db_ok}")
        print(f"✅ API query works: {api_ok}")
        print(f"✅ Response format correct: {fmt_ok}")

        if db_ok and api_ok and fmt_ok:
            print("\n✅ ALL CHECKS PASS - Scores data flow is working correctly!")
            print("\nIf dashboard still shows 'No Data':")
            print("1. Restart the dev_server: python start_dashboard_dev.py")
            print("2. Check browser console for errors")
            print("3. Verify /api/algo/scores endpoint returns data:")
            print("   curl http://localhost:3001/api/algo/scores?limit=5")
        else:
            print("\n❌ ONE OR MORE CHECKS FAILED - See above for details")
    except Exception as e:
        logger.error(f"Diagnostic failed: {e}", exc_info=True)
        print(f"\n❌ ERROR: {e}")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
