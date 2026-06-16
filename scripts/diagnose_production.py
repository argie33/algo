#!/usr/bin/env python3
"""Diagnose production revenue and growth data for key symbols."""
import sys, logging
logging.basicConfig(level=logging.WARNING)
from utils.db.context import DatabaseContext

SYMBOLS = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"]

with DatabaseContext("read") as cur:
    # What DB are we connected to?
    cur.execute("SELECT current_database(), inet_server_addr(), inet_server_port()")
    r = cur.fetchone()
    print(f"=== Connected to: db={r[0]} host={r[1]} port={r[2]} ===")
    print()

    print("=== Revenue by fiscal year for key symbols ===")
    cur.execute("""
        SELECT symbol, fiscal_year, revenue
        FROM annual_income_statement
        WHERE symbol = ANY(%s)
        ORDER BY symbol, fiscal_year DESC
    """, (SYMBOLS,))
    rows = cur.fetchall()
    cur_sym = None
    for r in rows:
        if r[0] != cur_sym:
            cur_sym = r[0]
            print(f"  {r[0]}:")
        rev = f"${float(r[2])/1e9:.1f}B" if r[2] else "NULL"
        print(f"    FY{r[1]}: {rev}")

    print()
    print("=== Growth metrics for key symbols ===")
    cur.execute("""
        SELECT symbol, revenue_growth_1y, revenue_growth_3y, revenue_growth_5y,
               eps_growth_1y, eps_growth_3y
        FROM growth_metrics
        WHERE symbol = ANY(%s)
        ORDER BY symbol
    """, (SYMBOLS,))
    rows = cur.fetchall()
    if not rows:
        print("  (no rows for these symbols)")
    for r in rows:
        print(f"  {r[0]}: rev_1y={r[1]} rev_3y={r[2]} rev_5y={r[3]} eps_1y={r[4]} eps_3y={r[5]}")

    print()
    print("=== Revenue NULL rate by fiscal year (across all symbols) ===")
    cur.execute("""
        SELECT fiscal_year,
               COUNT(*) FILTER (WHERE revenue IS NOT NULL) as has_rev,
               COUNT(*) as total,
               ROUND(100.0 * COUNT(*) FILTER (WHERE revenue IS NOT NULL) / COUNT(*), 0) as pct
        FROM annual_income_statement
        GROUP BY fiscal_year
        ORDER BY fiscal_year DESC
        LIMIT 15
    """)
    rows = cur.fetchall()
    for r in rows:
        print(f"  FY{r[0]}: {r[1]}/{r[2]} have revenue ({r[3]}%)")
