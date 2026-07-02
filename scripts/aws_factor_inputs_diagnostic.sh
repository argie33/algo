#!/bin/bash
# Quick diagnostic script for AWS factor inputs data
# Run this in AWS CloudShell to see what's actually in RDS

echo "=========================================="
echo "AWS FACTOR INPUTS DATA DIAGNOSTIC"
echo "=========================================="
echo ""

python3 << 'PYTHON_EOF'
import psycopg2
import json

try:
    conn = psycopg2.connect(
        host="algo-db.cojggi2mkthi.us-east-1.rds.amazonaws.com",
        port=5432,
        database="algo_prod",
        user="algo_admin",
        password="4$6QcbvV)vU(2G]hKEiY2mnj3L}>9Mxe",
        sslmode="require"
    )
    conn.autocommit = True
    cur = conn.cursor()

    print("[OK] Connected to AWS RDS\n")

    # Test 1: Quality Metrics
    print("1. QUALITY_METRICS (financial data source)")
    print("-" * 60)
    cur.execute("""
    SELECT COUNT(*) as total,
           COUNT(CASE WHEN roe IS NOT NULL THEN 1 END) as roe_count,
           COUNT(CASE WHEN operating_margin IS NOT NULL THEN 1 END) as op_margin_count,
           COUNT(CASE WHEN quality_score IS NOT NULL THEN 1 END) as score_count
    FROM quality_metrics
    """)
    row = cur.fetchone()
    if row:
        total, roe, op_margin, score = row
        print(f"  Total rows: {total:,}")
        print(f"  Rows with ROE: {roe:,} ({100*roe/total:.1f}%)" if total > 0 else "  Rows with ROE: 0")
        print(f"  Rows with Operating Margin: {op_margin:,} ({100*op_margin/total:.1f}%)" if total > 0 else "  Rows with Op Margin: 0")
        print(f"  Rows with Quality Score: {score:,} ({100*score/total:.1f}%)" if total > 0 else "  Rows with Score: 0")
    print()

    # Test 2: Growth Metrics
    print("2. GROWTH_METRICS (revenue/EPS growth source)")
    print("-" * 60)
    cur.execute("""
    SELECT COUNT(*) as total,
           COUNT(CASE WHEN revenue_growth_1y IS NOT NULL THEN 1 END) as growth_count,
           COUNT(CASE WHEN growth_score IS NOT NULL THEN 1 END) as score_count
    FROM growth_metrics
    """)
    row = cur.fetchone()
    if row:
        total, growth, score = row
        print(f"  Total rows: {total:,}")
        print(f"  Rows with Revenue Growth: {growth:,} ({100*growth/total:.1f}%)" if total > 0 else "  Rows with Growth: 0")
        print(f"  Rows with Growth Score: {score:,} ({100*score/total:.1f}%)" if total > 0 else "  Rows with Score: 0")
    print()

    # Test 3: Value Metrics
    print("3. VALUE_METRICS (P/E, P/B source)")
    print("-" * 60)
    cur.execute("""
    SELECT COUNT(*) as total,
           COUNT(CASE WHEN pe_ratio IS NOT NULL THEN 1 END) as pe_count,
           COUNT(CASE WHEN value_score IS NOT NULL THEN 1 END) as score_count
    FROM value_metrics
    """)
    row = cur.fetchone()
    if row:
        total, pe, score = row
        print(f"  Total rows: {total:,}")
        print(f"  Rows with P/E: {pe:,} ({100*pe/total:.1f}%)" if total > 0 else "  Rows with P/E: 0")
        print(f"  Rows with Value Score: {score:,} ({100*score/total:.1f}%)" if total > 0 else "  Rows with Score: 0")
    print()

    # Test 4: Stock Scores
    print("4. STOCK_SCORES (Final computed factors)")
    print("-" * 60)
    cur.execute("""
    SELECT COUNT(*) as total,
           COUNT(CASE WHEN composite_score IS NOT NULL THEN 1 END) as comp_count,
           COUNT(CASE WHEN quality_score IS NOT NULL THEN 1 END) as q_count,
           COUNT(CASE WHEN growth_score IS NOT NULL THEN 1 END) as g_count,
           COUNT(CASE WHEN value_score IS NOT NULL THEN 1 END) as v_count,
           COUNT(CASE WHEN positioning_score IS NOT NULL THEN 1 END) as p_count,
           ROUND(AVG(composite_score), 2) as avg_score
    FROM stock_scores
    """)
    row = cur.fetchone()
    if row:
        total, comp, q, g, v, p, avg = row
        print(f"  Total stock_scores: {total:,}")
        print(f"  With composite_score: {comp:,} ({100*comp/total:.1f}%)" if total > 0 else "  With composite: 0")
        print(f"  With quality_score: {q:,} ({100*q/total:.1f}%)" if total > 0 else "  With quality: 0")
        print(f"  With growth_score: {g:,} ({100*g/total:.1f}%)" if total > 0 else "  With growth: 0")
        print(f"  With value_score: {v:,} ({100*v/total:.1f}%)" if total > 0 else "  With value: 0")
        print(f"  With positioning_score: {p:,} ({100*p/total:.1f}%)" if total > 0 else "  With positioning: 0")
        print(f"  Average composite: {avg}")
    print()

    # Test 5: Sample stocks
    print("5. SAMPLE STOCKS (What API returns)")
    print("-" * 60)
    cur.execute("""
    SELECT sc.symbol, sc.composite_score, sc.quality_score, sc.growth_score,
           qm.roe, qm.operating_margin, gm.revenue_growth_1y, vm.pe_ratio
    FROM stock_scores sc
    LEFT JOIN quality_metrics qm ON qm.symbol = sc.symbol
    LEFT JOIN growth_metrics gm ON gm.symbol = sc.symbol
    LEFT JOIN value_metrics vm ON vm.symbol = sc.symbol
    WHERE sc.composite_score IS NOT NULL
    ORDER BY sc.composite_score DESC
    LIMIT 10
    """)

    rows = cur.fetchall()
    print(f"  {'Symbol':<8} | Composite | Quality | Growth | ROE | OpMar | RevGrow | P/E")
    print(f"  {'-'*70}")
    for row in rows:
        symbol, comp, q, g, roe, op, rev, pe = row
        q_str = f"{q:.1f}" if q else "NULL"
        g_str = f"{g:.1f}" if g else "NULL"
        roe_str = f"{roe:.1f}%" if roe else "NULL"
        op_str = f"{op:.1f}%" if op else "NULL"
        rev_str = f"{rev:.1f}%" if rev else "NULL"
        pe_str = f"{pe:.1f}" if pe else "NULL"
        print(f"  {symbol:<8} | {comp:>9.2f} | {q_str:>7} | {g_str:>6} | {roe_str:>6} | {op_str:>6} | {rev_str:>7} | {pe_str}")

    print()
    print("=" * 70)
    print("SUMMARY:")
    print("=" * 70)
    print()
    print("If you see:")
    print("  * quality_metrics > 1000 rows with roe/op_margin populated -> DATA IS THERE")
    print("  * growth_metrics > 1000 rows with revenue_growth populated -> DATA IS THERE")
    print("  * value_metrics > 1000 rows with pe_ratio populated -> DATA IS THERE")
    print("  * stock_scores > 4000 rows with composite_score -> SCORES COMPUTED")
    print()
    print("If you see:")
    print("  * All 0 rows in metric tables -> Loaders haven't run in AWS")
    print("  * All NULL values -> Migration 0044 columns exist but data wasn't populated")
    print()

    cur.close()
    conn.close()

except Exception as e:
    print(f"[ERROR] Connection failed: {e}")
    print()
    print("This means:")
    print("  1. AWS RDS is unreachable from CloudShell")
    print("  2. Network/security group misconfiguration")
    print("  3. RDS endpoint/credentials may be invalid")
    print()
    print("Next steps:")
    print("  1. Check RDS security groups allow CloudShell access")
    print("  2. Verify RDS endpoint is algo-db.cojggi2mkthi.us-east-1.rds.amazonaws.com")
    print("  3. Check password in steering/UNBLOCK_FINANCIAL_DATA.md")

PYTHON_EOF

echo ""
echo "=========================================="
echo "Diagnostic complete"
echo "=========================================="
