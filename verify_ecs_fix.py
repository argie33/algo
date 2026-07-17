#!/usr/bin/env python3
"""
Verify that the ECS task resource fix (CPU 512→1024, Memory 1024→2048)
resulted in improved factor score coverage.

Expected results:
- value_score coverage: ~80%+ (up from 78.5%)
- positioning_score coverage: ~81%+ (up from 0%)
"""

import psycopg2
from datetime import datetime, timedelta

try:
    conn = psycopg2.connect(
        dbname="stocks",
        user="stocks",
        host="localhost",
        port=5432
    )
    cursor = conn.cursor()

    print("=" * 70)
    print("ECS FIX VERIFICATION - Factor Score Coverage Analysis")
    print("=" * 70)

    # Check value_metrics freshness
    print("\n📊 ValueMetrics Table Status:")
    print("-" * 70)
    cursor.execute("""
        SELECT COUNT(*) as total_rows, MAX(updated_at) as latest_update
        FROM value_metrics
    """)
    total, latest = cursor.fetchone()
    print(f"  Total rows: {total}")
    print(f"  Latest update: {latest}")
    if latest:
        age = datetime.now(latest.tzinfo) - latest
        print(f"  Data age: {age.total_seconds() / 3600:.1f} hours")

    # Check factor score coverage
    print("\n⭐ Factor Score Coverage:")
    print("-" * 70)
    cursor.execute("""
        SELECT
          100.0 * COUNT(CASE WHEN value_score IS NOT NULL THEN 1 END) /
            NULLIF(COUNT(*), 0) as value_coverage_pct,
          100.0 * COUNT(CASE WHEN positioning_score IS NOT NULL THEN 1 END) /
            NULLIF(COUNT(*), 0) as positioning_coverage_pct,
          COUNT(*) as total_stocks,
          COUNT(CASE WHEN value_score IS NOT NULL THEN 1 END) as value_scored,
          COUNT(CASE WHEN positioning_score IS NOT NULL THEN 1 END) as positioning_scored
        FROM stock_scores
    """)
    row = cursor.fetchone()
    value_cov, positioning_cov, total, value_scored, positioning_scored = row

    print(f"  Total stocks: {total}")
    print(f"  Value Score coverage:       {value_cov:6.2f}% ({value_scored}/{total})")
    print(f"  Positioning Score coverage: {positioning_cov:6.2f}% ({positioning_scored}/{total})")

    # Expected baseline (before fix)
    print("\n  Expected improvement:")
    print(f"    Value Score:       78.5% → 80%+ ✅" if value_cov >= 80 else f"    Value Score:       78.5% → {value_cov:.1f}% ⏳")
    print(f"    Positioning Score: 0%   → 81%+ ✅" if positioning_cov >= 81 else f"    Positioning Score: 0%   → {positioning_cov:.1f}% ⏳")

    # Check for recent ValueMetrics updates (last 24 hours)
    print("\n📈 Recent ValueMetrics Updates (last 24h):")
    print("-" * 70)
    cursor.execute("""
        SELECT COUNT(*) as recent_updates
        FROM value_metrics
        WHERE updated_at > NOW() - INTERVAL '24 hours'
    """)
    recent = cursor.fetchone()[0]
    print(f"  Rows updated in last 24 hours: {recent}")

    # Check positioning_metrics
    print("\n📊 PositioningMetrics Table Status:")
    print("-" * 70)
    cursor.execute("""
        SELECT COUNT(*) as total_rows, MAX(updated_at) as latest_update
        FROM positioning_metrics
    """)
    pos_total, pos_latest = cursor.fetchone()
    print(f"  Total rows: {pos_total}")
    print(f"  Latest update: {pos_latest}")
    if pos_latest:
        age = datetime.now(pos_latest.tzinfo) - pos_latest
        print(f"  Data age: {age.total_seconds() / 3600:.1f} hours")

    # Final verdict
    print("\n" + "=" * 70)
    if value_cov >= 80 and positioning_cov >= 81:
        print("✅ ECS FIX VERIFIED - Factor scores fully recovered!")
    elif value_cov >= 80:
        print("✅ Value Score recovered, positioning still loading...")
    elif recent > 0:
        print("🔄 Metrics loading, check again in a few minutes...")
    else:
        print("❌ Metrics not yet updated, pipeline may still be running")
    print("=" * 70)

    conn.close()

except Exception as e:
    print(f"❌ Error: {e}")
    print("Make sure database is running: python3 lambda/api/dev_server.py")
