#!/usr/bin/env python3
"""Analyze signal quality impact of stale trend template data"""

from utils.db import DatabaseContext
from datetime import datetime, timedelta

with DatabaseContext('read') as cur:
    print("=" * 80)
    print("SIGNAL QUALITY ANALYSIS - IMPACT OF STALE TREND TEMPLATE DATA")
    print("=" * 80)

    # Get signals with quality scores from yesterday's run
    print("\nRECENT SIGNALS (last 24h) - Quality Score Distribution:")
    cur.execute("""
        SELECT quality_tier, COUNT(*) as count,
               ROUND(AVG(composite_score), 1) as avg_score,
               MIN(composite_score) as min_score,
               MAX(composite_score) as max_score
        FROM algo_signals
        WHERE created_at > NOW() - INTERVAL '24 hours'
        AND signal_date >= CURRENT_DATE - 1
        GROUP BY quality_tier
        ORDER BY quality_tier
    """)

    for tier, count, avg, min_s, max_s in cur.fetchall():
        print(f"\n  {tier}: {count} signals")
        print(f"    Avg score: {avg}, Range: {min_s}-{max_s}")

    # Check which signals were affected by stale trend template
    print("\n" + "=" * 80)
    print("SIGNALS AFFECTED BY STALE TREND TEMPLATE:")
    print("=" * 80)

    cur.execute("""
        SELECT symbol, composite_score, quality_tier, created_at
        FROM algo_signals
        WHERE created_at > NOW() - INTERVAL '24 hours'
        AND (signal_description LIKE '%degraded%'
             OR signal_description LIKE '%fallback%'
             OR signal_description LIKE '%stale%')
        ORDER BY composite_score DESC
    """)

    affected = cur.fetchall()
    if affected:
        print(f"\nFound {len(affected)} signals with degradation notes:")
        for sym, score, tier, created in affected[:10]:
            age = datetime.now() - created
            print(f"  {sym:6s}: score={score:3.0f}, tier={tier:8s}, created={age.total_seconds()/3600:.1f}h ago")
    else:
        print("\n✅ No signals with degradation notes found in last 24h")

    # Compare signal quality on days WITH vs WITHOUT trend template data
    print("\n" + "=" * 80)
    print("SIGNAL QUALITY COMPARISON:")
    print("=" * 80)

    cur.execute("""
        SELECT
            signal_date,
            COUNT(*) as signal_count,
            ROUND(AVG(composite_score), 1) as avg_score,
            COUNT(CASE WHEN composite_score >= 80 THEN 1 END) as high_quality
        FROM algo_signals
        WHERE signal_date >= CURRENT_DATE - 7
        GROUP BY signal_date
        ORDER BY signal_date DESC
    """)

    print("\n7-Day Signal Quality Trend:")
    for date, count, avg, high_q in cur.fetchall():
        print(f"  {date}: {count:3d} signals, avg={avg:5.1f}, high_quality={high_q:3d} ({100*high_q/count:.0f}%)")

    # Check trend_template_data freshness
    print("\n" + "=" * 80)
    print("TREND TEMPLATE DATA FRESHNESS:")
    print("=" * 80)

    cur.execute("""
        SELECT symbol, date, minervini_template, weinstein_template
        FROM trend_template_data
        WHERE date >= CURRENT_DATE - 2
        ORDER BY date DESC, symbol
        LIMIT 10
    """)

    rows = cur.fetchall()
    if rows:
        latest_date = rows[0][1]
        print(f"\nLatest trend data date: {latest_date}")
        print("\nSample of latest trend template values:")
        for sym, date, min_t, wein_t in rows:
            print(f"  {sym}: Minervini={min_t}, Weinstein={wein_t}")
    else:
        print("\n❌ No trend template data found!")

print("\n" + "=" * 80)
