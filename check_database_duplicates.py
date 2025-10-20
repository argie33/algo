#!/usr/bin/env python3
"""
Check for duplicate data in critical database tables.
User asked: "do we have dupes" and "where do we have dupes in our architecture"
"""
import psycopg2
from collections import defaultdict

conn = psycopg2.connect(
    host='localhost',
    port=5432,
    user='postgres',
    password='password',
    database='stocks'
)

cur = conn.cursor()

print("\n" + "="*80)
print("DUPLICATE DATA AUDIT - Checking for data integrity issues")
print("="*80 + "\n")

# Critical tables to check
tables_to_check = [
    {
        'name': 'stock_symbols',
        'id_col': 'symbol',
        'description': 'Source of truth for stocks (should be unique per symbol)'
    },
    {
        'name': 'stock_scores',
        'id_col': 'symbol',
        'description': 'Composite scores (should have at most 1 record per symbol)'
    },
    {
        'name': 'positioning_metrics',
        'id_cols': ['symbol', 'date'],
        'description': 'Position data (date-stamped, duplicates possible but suspicious)'
    },
    {
        'name': 'earnings_history',
        'id_cols': ['symbol', 'quarter'],
        'description': 'Earnings data (unique per symbol + quarter)'
    },
    {
        'name': 'stock_technical_indicators',
        'id_cols': ['symbol', 'date'],
        'description': 'Technical data (date-stamped)'
    },
    {
        'name': 'market_sentiment',
        'id_cols': ['symbol', 'date'],
        'description': 'Sentiment data (date-stamped)'
    },
]

total_duplicates = 0

for table_info in tables_to_check:
    table_name = table_info['name']
    description = table_info['description']

    # Check if table exists
    cur.execute("""
        SELECT EXISTS(
            SELECT FROM information_schema.tables
            WHERE table_name = %s
        )
    """, (table_name,))

    if not cur.fetchone()[0]:
        print(f"⚠️  TABLE NOT FOUND: {table_name}")
        continue

    # Get row count
    cur.execute(f"SELECT COUNT(*) FROM {table_name}")
    total_rows = cur.fetchone()[0]

    if total_rows == 0:
        print(f"⚠️  {table_name}: Empty table (0 rows)")
        continue

    # Check for duplicates
    if 'id_col' in table_info:
        id_col = table_info['id_col']
        cur.execute(f"""
            SELECT {id_col}, COUNT(*) as cnt
            FROM {table_name}
            GROUP BY {id_col}
            HAVING COUNT(*) > 1
            ORDER BY cnt DESC
        """)
    else:
        id_cols = ', '.join(table_info['id_cols'])
        cur.execute(f"""
            SELECT {id_cols}, COUNT(*) as cnt
            FROM {table_name}
            GROUP BY {id_cols}
            HAVING COUNT(*) > 1
            ORDER BY cnt DESC
        """)

    duplicates = cur.fetchall()

    print(f"\n{table_name}")
    print(f"  Description: {description}")
    print(f"  Total rows: {total_rows}")

    if duplicates:
        print(f"  ❌ DUPLICATES FOUND: {len(duplicates)} unique combinations with duplicates")
        total_duplicates += len(duplicates)

        for dup_row in duplicates[:10]:  # Show first 10
            if 'id_col' in table_info:
                id_val = dup_row[0]
                count = dup_row[1]
                print(f"     - {id_val}: {count} copies")
            else:
                id_vals = dup_row[:-1]
                count = dup_row[-1]
                print(f"     - {id_vals}: {count} copies")

        if len(duplicates) > 10:
            print(f"     ... and {len(duplicates) - 10} more")
    else:
        print(f"  ✅ NO DUPLICATES - All records unique by key")

print("\n" + "="*80)
print(f"SUMMARY: {total_duplicates} duplicate groups found across all tables")
print("="*80 + "\n")

# Specific checks for stock_scores table (critical for frontend)
print("\n" + "="*80)
print("DETAILED ANALYSIS: stock_scores table")
print("="*80 + "\n")

cur.execute("""
    SELECT symbol, COUNT(*) as cnt
    FROM stock_scores
    GROUP BY symbol
    HAVING COUNT(*) > 1
    ORDER BY cnt DESC
""")

score_dupes = cur.fetchall()
if score_dupes:
    print(f"❌ CRITICAL: {len(score_dupes)} symbols have multiple score records:")
    for symbol, cnt in score_dupes:
        print(f"   {symbol}: {cnt} records")
        # Show the duplicate records
        cur.execute(f"""
            SELECT id, symbol, composite_score, created_at
            FROM stock_scores
            WHERE symbol = %s
            ORDER BY created_at DESC
        """, (symbol,))
        for record in cur.fetchall():
            print(f"      - ID {record[0]}: score={record[2]}, created={record[3]}")
else:
    print("✅ stock_scores: Each symbol has exactly 1 record")

# Check for ETF contamination (should all be gone)
print("\n" + "="*80)
print("VERIFICATION: ETF Contamination Check")
print("="*80 + "\n")

etf_list = ['GLD', 'QQQ', 'IWM', 'SPY', 'VTI']
cur.execute(f"""
    SELECT symbol, COUNT(*)
    FROM stock_scores
    WHERE symbol IN ({','.join(['%s'] * len(etf_list))})
    GROUP BY symbol
""", etf_list)

etf_records = cur.fetchall()
if etf_records:
    print(f"❌ CRITICAL: Found {len(etf_records)} ETF records in stock_scores:")
    for symbol, cnt in etf_records:
        print(f"   {symbol}: {cnt} records (SHOULD BE 0)")
else:
    print("✅ ETFs properly removed: No ETF records in stock_scores")

cur.close()
conn.close()

print("\n✅ Duplicate check complete!\n")
