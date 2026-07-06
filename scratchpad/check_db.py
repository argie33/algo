#!/usr/bin/env python3
from utils.db.context import DatabaseContext
from datetime import datetime, timedelta

db = DatabaseContext('read')
with db as cur:
    # Check algo_positions schema
    print('=== algo_positions TABLE SCHEMA ===')
    cur.execute('''
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = 'algo_positions'
        ORDER BY ordinal_position
    ''')
    rows = cur.fetchall()
    for row in rows:
        print(f'{row["column_name"]}: {row["data_type"]}')

    # Check growth_score distribution
    print('\n=== GROWTH SCORE DATA DISTRIBUTION ===')
    cur.execute('''
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN growth_score IS NOT NULL THEN 1 ELSE 0 END) as with_score,
            SUM(CASE WHEN data_unavailable = TRUE THEN 1 ELSE 0 END) as unavailable,
            COUNT(DISTINCT symbol) as unique_symbols
        FROM stock_scores
    ''')
    rows = cur.fetchall()
    for row in rows:
        print(row)

    # Check top reasons for data unavailability
    print('\n=== TOP REASONS FOR UNAVAILABLE DATA ===')
    cur.execute('''
        SELECT reason, COUNT(*) as count
        FROM stock_scores
        WHERE data_unavailable = TRUE
        GROUP BY reason
        ORDER BY count DESC
        LIMIT 10
    ''')
    rows = cur.fetchall()
    for row in rows:
        print(row)
