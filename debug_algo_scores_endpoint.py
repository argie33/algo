#!/usr/bin/env python3
"""Debug why /api/algo/scores returns 0 items."""

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

# Test with the default sort_by from the endpoint
# sortBy not specified in the fetch_scores call, so it defaults to "composite_score"
# sortOrder defaults to "desc" if not specified

cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

# Check what the default parameters would be
sort_by = "composite_score"
sort_order = "desc"
sort_direction = "DESC" if sort_order == "desc" else "ASC"
limit = 50
offset = 0

query = f"""
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
    ORDER BY sc.{sort_by} {sort_direction}
    LIMIT %s OFFSET %s
)
SELECT
    fs.symbol,
    fs.composite_score,
    fs.data_completeness
FROM filtered_scores fs
ORDER BY fs.{sort_by} {sort_direction}
"""

cur.execute(query, [limit, offset])
rows = cur.fetchall()
print(f"Query with default params returned {len(rows)} rows")

if len(rows) == 0:
    # Test without data_completeness filter
    query2 = """
    WITH filtered_scores AS (
        SELECT sc.*, ss.security_name, ss.is_sp500
        FROM stock_scores sc
        JOIN stock_symbols ss ON ss.symbol = sc.symbol
        WHERE sc.composite_score > 0
        AND ss.symbol NOT IN (SELECT symbol FROM etf_symbols)
        AND (sc.data_unavailable = false OR sc.data_unavailable IS NULL)
        LIMIT 50 OFFSET 0
    )
    SELECT COUNT(*) as count FROM filtered_scores
    """
    cur.execute(query2)
    count = cur.fetchone()
    print(f"Without data_completeness filter: {count['count']} rows")

    # Test the component conditions
    cur.execute("SELECT COUNT(*) FROM stock_scores WHERE composite_score > 0")
    print(f"composite_score > 0: {cur.fetchone()[0]}")

    cur.execute("""SELECT COUNT(*) FROM stock_scores ss
    WHERE ss.symbol NOT IN (SELECT symbol FROM etf_symbols)""")
    print(f"NOT in etf_symbols: {cur.fetchone()[0]}")

    cur.execute("""SELECT COUNT(*) FROM stock_scores
    WHERE data_completeness >= 70""")
    print(f"data_completeness >= 70: {cur.fetchone()[0]}")

    cur.execute("""SELECT COUNT(*) FROM stock_scores
    WHERE data_unavailable = false OR data_unavailable IS NULL""")
    print(f"NOT data_unavailable: {cur.fetchone()[0]}")

conn.close()
