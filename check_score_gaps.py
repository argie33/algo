#!/usr/bin/env python3
"""
Check why value_score and other scores have NULL values
"""
import psycopg2
import os

try:
    conn = psycopg2.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        port=int(os.environ.get("DB_PORT", "5432")),
        user=os.environ.get("DB_USER", "postgres"),
        password=os.environ.get("DB_PASSWORD", "password"),
        dbname=os.environ.get("DB_NAME", "stocks"),
    )
    cur = conn.cursor()

    print("\n" + "="*80)
    print("STOCK SCORE NULL VALUE ANALYSIS")
    print("="*80)

    # Check value_score gaps
    cur.execute("""
        SELECT
            COUNT(*) as total,
            COUNT(CASE WHEN value_score IS NOT NULL THEN 1 END) as with_score,
            COUNT(CASE WHEN value_score IS NULL THEN 1 END) as without_score
        FROM stock_scores
    """)
    row = cur.fetchone()
    print(f"\n📊 STOCK SCORES TABLE")
    print(f"   Total: {row[0]:,} | With value_score: {row[1]:,} | Without: {row[2]:,} ({100*row[2]/row[0]:.1f}%)")

    # Check what inputs are available when value_score is NULL
    cur.execute("""
        SELECT
            COUNT(CASE WHEN km.trailing_pe IS NOT NULL THEN 1 END) as has_pe,
            COUNT(CASE WHEN km.price_to_book IS NOT NULL THEN 1 END) as has_pb,
            COUNT(CASE WHEN km.debt_to_equity IS NOT NULL THEN 1 END) as has_de,
            COUNT(CASE WHEN km.dividend_yield IS NOT NULL THEN 1 END) as has_div
        FROM stock_scores ss
        LEFT JOIN key_metrics km ON ss.symbol = km.ticker
        WHERE ss.value_score IS NULL
    """)
    row = cur.fetchone()
    print(f"\n   When value_score IS NULL, available inputs:")
    print(f"   - PE Ratio: {row[0]:,}")
    print(f"   - Price/Book: {row[1]:,}")
    print(f"   - Debt/Equity: {row[2]:,}")
    print(f"   - Dividend Yield: {row[3]:,}")

    # Check each score's NULL rate
    print(f"\n📊 SCORE NULL RATES BY FACTOR")
    scores = ['momentum_score', 'growth_score', 'quality_score', 'stability_score', 'positioning_score', 'composite_score']

    for score in scores:
        cur.execute(f"""
            SELECT
                COUNT(*) as total,
                COUNT(CASE WHEN {score} IS NULL THEN 1 END) as null_count
            FROM stock_scores
        """)
        total, null_count = cur.fetchone()
        pct = 100 * null_count / total if total > 0 else 0
        status = "❌" if pct > 50 else "⚠️ " if pct > 20 else "✅"
        print(f"   {status} {score:25s}: {pct:5.1f}% NULL ({null_count:,}/{total:,})")

    # Check for anomalies - stocks with some scores but not others
    cur.execute("""
        SELECT
            symbol,
            momentum_score,
            growth_score,
            value_score,
            quality_score,
            stability_score,
            positioning_score,
            composite_score
        FROM stock_scores
        WHERE
            (momentum_score IS NOT NULL AND value_score IS NULL)
            OR (growth_score IS NOT NULL AND value_score IS NULL)
        LIMIT 5
    """)

    rows = cur.fetchall()
    if rows:
        print(f"\n📊 EXAMPLES: Stocks with SOME scores but NO value_score")
        for row in rows:
            print(f"   {row[0]:8s} - Mom:{row[1]}, Growth:{row[2]}, Value:{row[3]}, Qual:{row[4]}, Stab:{row[5]}")

    cur.close()
    conn.close()

except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
