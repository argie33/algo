#!/usr/bin/env python3
"""
Quick test script to verify percentile-based quality score calculation
"""

import psycopg2
import os

def get_db_connection():
    # Use environment variables or defaults for database connection
    return psycopg2.connect(
        host=os.environ.get('DB_HOST', 'localhost'),
        database=os.environ.get('DB_NAME', 'stocks'),
        user=os.environ.get('DB_USER', 'postgres'),
        password=os.environ.get('DB_PASSWORD', 'password'),
        port=os.environ.get('DB_PORT', 5432)
    )

def main():
    conn = get_db_connection()
    cur = conn.cursor()

    # Get a sample of stocks with their quality scores
    test_symbols = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA',
                    'WMT', 'JPM', 'JNJ', 'V', 'PG', 'MA', 'HD', 'CVX']

    print("📊 Testing Quality Scores for Sample Stocks")
    print("=" * 80)

    for symbol in test_symbols:
        cur.execute("""
            SELECT quality_score, composite_score, value_score, growth_score, momentum_score
            FROM stock_scores
            WHERE symbol = %s
        """, (symbol,))

        result = cur.fetchone()
        if result:
            quality, composite, value, growth, momentum = result
            print(f"{symbol:8} | Quality: {quality:6.2f} | Value: {value:6.2f} | "
                  f"Growth: {growth:6.2f} | Momentum: {momentum:6.2f} | Composite: {composite:6.2f}")
        else:
            print(f"{symbol:8} | No data in stock_scores table")

    print("\n" + "=" * 80)

    # Get overall statistics
    cur.execute("""
        SELECT
            COUNT(*) as total_stocks,
            AVG(quality_score) as avg_quality,
            MIN(quality_score) as min_quality,
            MAX(quality_score) as max_quality,
            STDDEV(quality_score) as std_quality,
            PERCENTILE_CONT(0.25) WITHIN GROUP (ORDER BY quality_score) as q1_quality,
            PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY quality_score) as median_quality,
            PERCENTILE_CONT(0.75) WITHIN GROUP (ORDER BY quality_score) as q3_quality
        FROM stock_scores
        WHERE quality_score IS NOT NULL
    """)

    stats = cur.fetchone()
    if stats:
        total, avg, min_val, max_val, std, q1, median, q3 = stats
        print(f"\n📈 Overall Quality Score Statistics (from {total} stocks):")
        print(f"   Average:    {avg:6.2f}")
        print(f"   Std Dev:    {std:6.2f}")
        print(f"   Min:        {min_val:6.2f}")
        print(f"   Q1 (25%):   {q1:6.2f}")
        print(f"   Median:     {median:6.2f}")
        print(f"   Q3 (75%):   {q3:6.2f}")
        print(f"   Max:        {max_val:6.2f}")

    cur.close()
    conn.close()

if __name__ == "__main__":
    main()
