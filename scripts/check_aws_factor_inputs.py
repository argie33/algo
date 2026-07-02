#!/usr/bin/env python3
"""
Check what factor input data is actually visible in AWS RDS.
Focus on the metric tables that feed into stock_scores.
"""

import sys
import os

sys.path.insert(0, '.')

# Force AWS connection by setting environment
os.environ['ALGO_ENV'] = 'production'

from utils.db.context import DatabaseContext

print("\n" + "="*80)
print("AWS FACTOR INPUTS DATA CHECK")
print("="*80 + "\n")

try:
    # Check connection
    with DatabaseContext("read") as cur:
        cur.execute("SELECT inet_server_addr(), current_database()")
        host, db = cur.fetchone()
        print(f"Connected to: {host} / {db}\n")

        if 'rds.amazonaws.com' not in str(host):
            print("WARNING: Not connected to AWS RDS!\n")

    # Check factor input metrics completeness
    print("FACTOR INPUT METRICS (Metric Tables)")
    print("-" * 80)

    metrics_tables = {
        'quality_metrics': {
            'key_cols': ['quality_score', 'operating_margin', 'net_margin'],
            'threshold': 65
        },
        'growth_metrics': {
            'key_cols': ['growth_score', 'revenue_growth', 'earnings_growth'],
            'threshold': 70
        },
        'value_metrics': {
            'key_cols': ['value_score', 'pe_ratio', 'pb_ratio'],
            'threshold': 80
        },
        'positioning_metrics': {
            'key_cols': ['positioning_score', 'insider_ownership', 'institutional_ownership'],
            'threshold': 70
        },
        'stability_metrics': {
            'key_cols': ['stability_score', 'volatility', 'beta'],
            'threshold': 85
        }
    }

    with DatabaseContext("read") as cur:
        for table_name, config in metrics_tables.items():
            cur.execute(f"""
                SELECT
                    COUNT(*) as total,
                    COUNT(CASE WHEN data_unavailable = false OR data_unavailable IS NULL THEN 1 END) as available,
                    COUNT(CASE WHEN data_unavailable = true THEN 1 END) as unavailable
                FROM {table_name}
            """)
            total, available, unavailable = cur.fetchone()
            pct = (available / total * 100) if total > 0 else 0
            status = "[OK]" if pct >= config['threshold'] else "[WARN]" if pct >= config['threshold']*0.8 else "[FAIL]"

            print(f"{status} {table_name:25} | {total:5,} rows | {available:5,} available ({pct:5.1f}%) | {unavailable:5,} unavailable")

    print("\n" + "="*80)
    print("FACTOR SCORES (Computed from Metric Inputs)")
    print("-" * 80)

    with DatabaseContext("read") as cur:
        # Overall stats
        cur.execute("""
            SELECT
                COUNT(*) as total,
                COUNT(CASE WHEN composite_score IS NOT NULL THEN 1 END) as with_composite,
                COUNT(CASE WHEN quality_score IS NOT NULL THEN 1 END) as q,
                COUNT(CASE WHEN growth_score IS NOT NULL THEN 1 END) as g,
                COUNT(CASE WHEN value_score IS NOT NULL THEN 1 END) as v,
                COUNT(CASE WHEN positioning_score IS NOT NULL THEN 1 END) as p,
                COUNT(CASE WHEN stability_score IS NOT NULL THEN 1 END) as s,
                COUNT(CASE WHEN momentum_score IS NOT NULL THEN 1 END) as m,
                ROUND(AVG(composite_score), 2) as avg_score,
                COUNT(CASE WHEN data_unavailable = true THEN 1 END) as marked_unavailable
            FROM stock_scores
        """)

        total, with_comp, q, g, v, p, s, m, avg, unavail = cur.fetchone()

        print(f"Total records: {total:,}")
        print(f"With composite_score: {with_comp:,} ({100*with_comp/total:.1f}%)")
        print(f"Average composite: {avg}")
        print(f"Marked data_unavailable: {unavail:,}")
        print()
        print(f"Factor coverage:")
        print(f"  Quality:     {q:5,} ({100*q/total:5.1f}%)")
        print(f"  Growth:      {g:5,} ({100*g/total:5.1f}%)")
        print(f"  Value:       {v:5,} ({100*v/total:5.1f}%)")
        print(f"  Positioning: {p:5,} ({100*p/total:5.1f}%)")
        print(f"  Stability:   {s:5,} ({100*s/total:5.1f}%)")
        print(f"  Momentum:    {m:5,} ({100*m/total:5.1f}%)")

    print("\n" + "="*80)
    print("SAMPLE STOCKS WITH MISSING FACTOR INPUTS")
    print("-" * 80)

    with DatabaseContext("read") as cur:
        # Find stocks with low factor coverage
        cur.execute("""
            SELECT symbol, composite_score,
                CASE WHEN quality_score IS NOT NULL THEN 'Y' ELSE 'N' END as q,
                CASE WHEN growth_score IS NOT NULL THEN 'Y' ELSE 'N' END as g,
                CASE WHEN value_score IS NOT NULL THEN 'Y' ELSE 'N' END as v,
                CASE WHEN positioning_score IS NOT NULL THEN 'Y' ELSE 'N' END as p,
                CASE WHEN stability_score IS NOT NULL THEN 'Y' ELSE 'N' END as s,
                CASE WHEN momentum_score IS NOT NULL THEN 'Y' ELSE 'N' END as m,
                data_unavailable
            FROM stock_scores
            WHERE composite_score IS NOT NULL
            ORDER BY
                (CASE WHEN quality_score IS NULL THEN 1 ELSE 0 END +
                 CASE WHEN growth_score IS NULL THEN 1 ELSE 0 END +
                 CASE WHEN value_score IS NULL THEN 1 ELSE 0 END +
                 CASE WHEN positioning_score IS NULL THEN 1 ELSE 0 END +
                 CASE WHEN stability_score IS NULL THEN 1 ELSE 0 END +
                 CASE WHEN momentum_score IS NULL THEN 1 ELSE 0 END) DESC
            LIMIT 15
        """)

        print(f"{'Symbol':<8} | Score | Q G V P S M | Marked Unavail")
        print("-" * 60)
        for row in cur.fetchall():
            symbol, score, q, g, v, p, s, m, unavail = row
            factors = f"{q} {g} {v} {p} {s} {m}"
            unavail_flag = "YES" if unavail else "NO"
            print(f"{symbol:<8} | {score:5.1f} | {factors} | {unavail_flag}")

    print("\n[OK] AWS factor inputs check complete\n")

except Exception as e:
    print(f"[ERROR] {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
