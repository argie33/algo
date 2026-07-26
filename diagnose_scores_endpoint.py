#!/usr/bin/env python3
"""Diagnose why scores endpoint returns 0 items."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path.cwd()))

import psycopg2
import psycopg2.extras

db_host = os.getenv("DB_HOST") or "localhost"
db_port = int(os.getenv("DB_PORT") or 5432)
db_user = os.getenv("DB_USER") or "postgres"
db_password = os.getenv("DB_PASSWORD")
db_name = os.getenv("DB_NAME") or "stocks"

conn = psycopg2.connect(
    host=db_host, port=db_port, user=db_user, password=db_password, dbname=db_name
)
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

# Run the EXACT query the endpoint runs (simplified CTE version)
query = """
WITH max_price_date AS (
    SELECT MAX(date) AS max_date FROM price_daily
),
filtered_scores AS (
    SELECT sc.*, ss.security_name, ss.is_sp500
    FROM stock_scores sc
    JOIN stock_symbols ss ON ss.symbol = sc.symbol
    WHERE sc.composite_score > 0
    AND ss.symbol NOT IN (SELECT symbol FROM etf_symbols)
    AND sc.data_completeness >= 70
    AND (sc.data_unavailable = false OR sc.data_unavailable IS NULL)
    ORDER BY sc.composite_score DESC
    LIMIT 5 OFFSET 0
)
SELECT
    fs.symbol,
    COALESCE(fs.security_name, fs.symbol) AS company_name,
    fs.composite_score, fs.momentum_score, fs.quality_score,
    fs.value_score, fs.growth_score, fs.positioning_score, fs.stability_score,
    fs.data_completeness,
    fs.updated_at
FROM filtered_scores fs
LEFT JOIN company_profile cp ON cp.ticker = fs.symbol
ORDER BY fs.composite_score DESC
"""

try:
    cur.execute(query)
    rows = cur.fetchall()
    print(f"Query returned {len(rows)} rows")
    for i, row in enumerate(rows):
        print(f"  Row {i}: symbol={row['symbol']} composite={row['composite_score']}")
        print(f"         data_completeness={row['data_completeness']}")
except Exception as e:
    print(f"ERROR: {type(e).__name__}: {e}")
    import traceback

    traceback.print_exc()

conn.close()
