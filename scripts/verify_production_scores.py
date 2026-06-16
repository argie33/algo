#!/usr/bin/env python3
"""Full production verification: revenue population + scores across all symbols."""
import sys
import logging
logging.basicConfig(level=logging.WARNING)

from utils.db.context import DatabaseContext

with DatabaseContext("read") as cur:
    print("=== Revenue coverage (annual_income_statement) ===")
    cur.execute("""
        SELECT
            COUNT(*) FILTER (WHERE revenue IS NOT NULL) as with_revenue,
            COUNT(*) FILTER (WHERE revenue IS NULL) as null_revenue,
            COUNT(*) as total_rows,
            COUNT(DISTINCT symbol) as total_symbols,
            COUNT(DISTINCT symbol) FILTER (WHERE revenue IS NOT NULL) as symbols_with_revenue
        FROM annual_income_statement
    """)
    r = cur.fetchone()
    null_pct = r[1] / r[2] * 100 if r[2] else 0
    print(f"  Symbols with revenue: {r[4]}/{r[3]}")
    print(f"  Rows: {r[0]} with revenue, {r[1]} NULL ({null_pct:.1f}% NULL)")

    print()
    print("=== Stock scores coverage ===")
    cur.execute("""
        SELECT
            COUNT(*) as total,
            COUNT(*) FILTER (WHERE quality_score > 0) as has_quality,
            COUNT(*) FILTER (WHERE growth_score > 0) as has_growth,
            COUNT(*) FILTER (WHERE positioning_score > 0) as has_positioning,
            COUNT(*) FILTER (WHERE composite_score > 0) as has_composite,
            ROUND(AVG(composite_score)::numeric, 1) as avg_composite,
            ROUND(AVG(quality_score)::numeric, 1) as avg_quality,
            ROUND(AVG(growth_score)::numeric, 1) as avg_growth
        FROM stock_scores
    """)
    r = cur.fetchone()
    print(f"  Total scored symbols: {r[0]}")
    print(f"  Has quality score:    {r[1]} ({r[1]/r[0]*100:.0f}%)" if r[0] else "  (none)")
    print(f"  Has growth score:     {r[2]} ({r[2]/r[0]*100:.0f}%)" if r[0] else "")
    print(f"  Has positioning:      {r[3]} ({r[3]/r[0]*100:.0f}%)" if r[0] else "")
    print(f"  Has composite:        {r[4]} ({r[4]/r[0]*100:.0f}%)" if r[0] else "")
    print(f"  Avg composite score:  {r[5]}")
    print(f"  Avg quality score:    {r[6]}")
    print(f"  Avg growth score:     {r[7]}")

    print()
    print("=== Top 10 stocks by composite score ===")
    cur.execute("""
        SELECT symbol, composite_score, quality_score, growth_score, positioning_score, data_completeness
        FROM stock_scores
        ORDER BY composite_score DESC
        LIMIT 10
    """)
    rows = cur.fetchall()
    for r in rows:
        print(f"  {r[0]:<6} composite={r[1]:.1f}  quality={r[2]:.1f}  growth={r[3]:.1f}  positioning={r[4]:.1f}  completeness={r[5]:.0f}%")

    print()
    print("=== Key symbols (AAPL MSFT GOOGL AMZN NVDA) ===")
    cur.execute("""
        SELECT symbol, composite_score, quality_score, growth_score, positioning_score, data_completeness
        FROM stock_scores
        WHERE symbol IN ('AAPL','MSFT','GOOGL','AMZN','NVDA')
        ORDER BY symbol
    """)
    rows = cur.fetchall()
    for r in rows:
        print(f"  {r[0]:<6} composite={r[1]:.1f}  quality={r[2]:.1f}  growth={r[3]:.1f}  positioning={r[4]:.1f}  completeness={r[5]:.0f}%")

    print()
    print("=== Growth metrics coverage ===")
    cur.execute("""
        SELECT
            COUNT(*) as total,
            COUNT(*) FILTER (WHERE revenue_growth_1y IS NOT NULL) as has_rev_growth_1y,
            COUNT(*) FILTER (WHERE revenue_growth_3y IS NOT NULL) as has_rev_growth_3y
        FROM growth_metrics
    """)
    r = cur.fetchone()
    print(f"  Total symbols: {r[0]}")
    print(f"  Has 1Y revenue growth: {r[1]}")
    print(f"  Has 3Y revenue growth: {r[2]}")
