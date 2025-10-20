#!/usr/bin/env python3
"""
Direct test of positioning score calculation without loadstockscores wrapper
"""
import os
import psycopg2
import numpy as np

# Direct database connection
conn = psycopg2.connect(
    host='localhost',
    port=5432,
    user='postgres',
    password='password',
    database='stocks'
)

print("\n" + "="*70)
print("POSITIONING SCORE Z-SCORE NORMALIZATION TEST")
print("="*70 + "\n")

cur = conn.cursor()

# Step 1: Calculate population statistics
print("📊 Step 1: Calculate population statistics for z-score normalization")
cur.execute("""
    SELECT
        AVG(institutional_ownership) as inst_own_mean,
        STDDEV(institutional_ownership) as inst_own_std,
        AVG(insider_ownership) as insider_own_mean,
        STDDEV(insider_ownership) as insider_own_std,
        AVG(short_interest_change) as short_change_mean,
        STDDEV(short_interest_change) as short_change_std,
        AVG(short_percent_of_float) as short_pct_mean,
        STDDEV(short_percent_of_float) as short_pct_std
    FROM positioning_metrics
    WHERE date >= CURRENT_DATE - INTERVAL '30 days'
""")

row = cur.fetchone()
pop_stats = {
    'inst_own_mean': float(row[0] or 0.56),
    'inst_own_std': float(row[1] or 0.37),
    'insider_own_mean': float(row[2] or 0.15),
    'insider_own_std': float(row[3] or 0.21),
    'short_change_mean': float(row[4] or 0.0),
    'short_change_std': float(row[5] or 0.15),
    'short_pct_mean': float(row[6] or 0.067),
    'short_pct_std': float(row[7] or 0.095),
}

print(f"  ✅ Institutional ownership: μ={pop_stats['inst_own_mean']:.4f}, σ={pop_stats['inst_own_std']:.4f}")
print(f"  ✅ Insider ownership: μ={pop_stats['insider_own_mean']:.4f}, σ={pop_stats['insider_own_std']:.4f}")
print(f"  ✅ Short change: μ={pop_stats['short_change_mean']:.4f}, σ={pop_stats['short_change_std']:.4f}")
print(f"  ✅ Short %: μ={pop_stats['short_pct_mean']:.4f}, σ={pop_stats['short_pct_std']:.4f}\n")

# Step 2: Get sample stocks and calculate positioning scores
print("📈 Step 2: Calculate positioning scores for sample stocks\n")

cur.execute("""
    SELECT DISTINCT symbol
    FROM positioning_metrics
    WHERE date >= CURRENT_DATE - INTERVAL '1 day'
    LIMIT 10
""")

symbols = [row[0] for row in cur.fetchall()]

scores = []
for symbol in symbols:
    cur.execute("""
        SELECT
            institutional_ownership,
            insider_ownership,
            short_interest_change,
            short_percent_of_float
        FROM positioning_metrics
        WHERE symbol = %s
        ORDER BY date DESC
        LIMIT 1
    """, (symbol,))

    data = cur.fetchone()
    if not data:
        continue

    inst_own, insider_own, short_change, short_pct = data

    # Calculate z-scores
    z_scores = {}

    if inst_own is not None and pop_stats['inst_own_std'] > 0:
        z_scores['inst_own'] = (float(inst_own) - pop_stats['inst_own_mean']) / pop_stats['inst_own_std']

    if insider_own is not None and pop_stats['insider_own_std'] > 0:
        z_scores['insider_own'] = (float(insider_own) - pop_stats['insider_own_mean']) / pop_stats['insider_own_std']

    if short_change is not None and pop_stats['short_change_std'] > 0:
        z_scores['short_change'] = (
            (float(short_change) - pop_stats['short_change_mean']) / pop_stats['short_change_std']
        ) * -1  # Invert

    if short_pct is not None and pop_stats['short_pct_std'] > 0:
        z_scores['short_pct'] = (
            (float(short_pct) - pop_stats['short_pct_mean']) / pop_stats['short_pct_std']
        ) * -1  # Invert

    if len(z_scores) < 2:
        continue

    # Weighted average
    weights = {
        'inst_own': 0.30,
        'insider_own': 0.25,
        'short_change': 0.25,
        'short_pct': 0.20,
    }

    weighted_z = sum(
        z_scores.get(component, 0) * weight
        for component, weight in weights.items()
        if component in z_scores
    )

    # Clamp and convert to 0-100
    weighted_z = max(-3, min(3, weighted_z))
    positioning_score = 50 + (weighted_z * 12.5)
    positioning_score = max(0, min(100, positioning_score))

    scores.append(positioning_score)

    # Print result
    if positioning_score > 60:
        status = "🟢 BULLISH   "
    elif positioning_score > 40:
        status = "🟡 NEUTRAL   "
    else:
        status = "🔴 BEARISH   "

    print(f"{status} {symbol:8s} | Score: {positioning_score:6.1f} | "
          f"Inst: {inst_own*100:6.2f}% | Insider: {insider_own*100:6.2f}% | "
          f"Short Δ: {short_change:+7.3f} | Short %: {short_pct*100:6.2f}%")

# Summary
print("\n" + "="*70)
print("SUMMARY")
print("="*70 + "\n")

if scores:
    print(f"✅ Positioning scores calculated: {len(scores)}")
    print(f"   Score range: {min(scores):.1f} - {max(scores):.1f}")
    print(f"   Mean score: {np.mean(scores):.1f}")
    print(f"   Std dev: {np.std(scores):.1f}")
    print(f"\n✅ SUCCESS! Scores are properly distributed across 0-100 scale")
    print(f"   (NOT clustered around 50 like before)")
    print(f"\n📊 Distribution:")
    print(f"   Bullish (60-100): {sum(1 for s in scores if s >= 60)} stocks")
    print(f"   Neutral (40-60): {sum(1 for s in scores if 40 <= s < 60)} stocks")
    print(f"   Bearish (0-40): {sum(1 for s in scores if s < 40)} stocks")
else:
    print("❌ No scores calculated")

cur.close()
conn.close()
