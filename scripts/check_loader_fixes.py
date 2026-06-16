#!/usr/bin/env python3
"""Verify loader fix results: revenue population and score accuracy."""
import sys
import logging
logging.basicConfig(level=logging.WARNING)

from utils.db.context import DatabaseContext

SYMBOLS = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"]

with DatabaseContext("read") as cur:
    print("=== Revenue in annual_income_statement ===")
    cur.execute("""
        SELECT symbol, fiscal_year, revenue
        FROM annual_income_statement
        WHERE symbol = ANY(%s)
        ORDER BY symbol, fiscal_year DESC
    """, (SYMBOLS,))
    rows = cur.fetchall()
    if not rows:
        print("  (no rows)")
    for r in rows[:20]:
        rev = f"${float(r[2])/1e9:.1f}B" if r[2] else "NULL"
        print(f"  {r[0]}  FY{r[1]}  revenue={rev}")

    print()
    print("=== Quality metrics ===")
    cur.execute("""
        SELECT symbol, operating_margin, net_margin, roe, roa
        FROM quality_metrics
        WHERE symbol = ANY(%s)
        ORDER BY symbol
    """, (SYMBOLS,))
    rows = cur.fetchall()
    if not rows:
        print("  (no rows)")
    for r in rows:
        print(f"  {r[0]}  op_margin={r[1]}  net_margin={r[2]}  roe={r[3]}  roa={r[4]}")

    print()
    print("=== Stock scores ===")
    cur.execute("""
        SELECT symbol, composite_score, quality_score, positioning_score, growth_score
        FROM stock_scores
        WHERE symbol = ANY(%s)
        ORDER BY symbol
    """, (SYMBOLS,))
    rows = cur.fetchall()
    if not rows:
        print("  (no rows)")
    for r in rows:
        print(f"  {r[0]}  composite={r[1]}  quality={r[2]}  positioning={r[3]}  growth={r[4]}")

    print()
    print("=== NULL revenue rate ===")
    cur.execute("""
        SELECT
            COUNT(*) FILTER (WHERE revenue IS NULL) as null_count,
            COUNT(*) as total
        FROM annual_income_statement
        WHERE symbol = ANY(%s)
    """, (SYMBOLS,))
    r = cur.fetchone()
    pct = r[0] / r[1] * 100 if r[1] else 0
    print(f"  NULL revenue: {r[0]}/{r[1]} rows ({pct:.0f}%)")
