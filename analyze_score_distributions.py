#!/usr/bin/env python3
"""
Analyze score distributions to identify clustering problems
and determine which factors need z-score normalization.
"""
import os
import psycopg2
import numpy as np
from collections import Counter

# Direct database connection
conn = psycopg2.connect(
    host='localhost',
    port=5432,
    user='postgres',
    password='password',
    database='stocks'
)

print("\n" + "="*80)
print("SCORE DISTRIBUTION ANALYSIS - Identifying Clustering Problems")
print("="*80 + "\n")

cur = conn.cursor()

# Get all available scores from the database
cur.execute("""
    SELECT
        composite_score, momentum_score, value_score, quality_score,
        growth_score, positioning_score
    FROM stock_scores
    WHERE composite_score IS NOT NULL
    LIMIT 1000
""")

scores = cur.fetchall()

if not scores:
    print("❌ No scores found in database")
    cur.close()
    conn.close()
    exit(1)

print(f"📊 Analyzed {len(scores)} stocks with complete score data\n")

# Analyze each factor
factors = [
    ('composite_score', 'COMPOSITE SCORE'),
    ('momentum_score', 'MOMENTUM SCORE (RSI-based)'),
    ('value_score', 'VALUE SCORE (PE-based)'),
    ('quality_score', 'QUALITY SCORE (volatility+volume)'),
    ('growth_score', 'GROWTH SCORE (earnings+price)'),
    ('positioning_score', 'POSITIONING SCORE (z-score normalized)')
]

for idx, (col_name, label) in enumerate(factors):
    values = [float(score[idx]) for score in scores if score[idx] is not None]

    if not values:
        print(f"⚠️  {label}: NO DATA AVAILABLE")
        continue

    values = np.array(values)

    # Statistics
    mean = np.mean(values)
    std = np.std(values)
    min_val = np.min(values)
    max_val = np.max(values)
    median = np.median(values)

    # Count distinct values
    distinct_count = len(set(values))

    # Check for clustering around mean (coefficient of variation)
    if mean > 0:
        cv = (std / mean) * 100  # Coefficient of variation
    else:
        cv = 0

    # Quartiles for distribution analysis
    q1 = np.percentile(values, 25)
    q3 = np.percentile(values, 75)
    iqr = q3 - q1

    print(f"{'='*80}")
    print(f"{label}")
    print(f"{'='*80}")
    print(f"  Count:              {len(values)} stocks")
    print(f"  Range:              {min_val:.1f} - {max_val:.1f}")
    print(f"  Mean:               {mean:.2f}")
    print(f"  Median:             {median:.2f}")
    print(f"  Std Dev:            {std:.2f}")
    print(f"  CV (Coeff Var):     {cv:.1f}%")
    print(f"  Quartile 1:         {q1:.2f}")
    print(f"  Quartile 3:         {q3:.2f}")
    print(f"  IQR:                {iqr:.2f}")
    print(f"  Distinct Values:    {distinct_count}")

    # Distribution assessment
    print(f"\n  📈 Distribution Assessment:")
    if cv < 10:
        print(f"     ❌ SEVERE CLUSTERING - CV={cv:.1f}% (need z-score normalization)")
    elif cv < 20:
        print(f"     ⚠️  MODERATE CLUSTERING - CV={cv:.1f}% (consider z-score normalization)")
    elif cv < 30:
        print(f"     ⚠️  MILD CLUSTERING - CV={cv:.1f}% (watch for optimization)")
    else:
        print(f"     ✅ WELL DISTRIBUTED - CV={cv:.1f}% (acceptable)")

    # Check if mostly discrete values
    if distinct_count < 20:
        value_counts = Counter(values)
        top_values = value_counts.most_common(5)
        print(f"\n  🎯 Top 5 Score Values (discrete distribution):")
        for val, count in top_values:
            pct = (count / len(values)) * 100
            print(f"     {val:.2f}: {count} stocks ({pct:.1f}%)")

    # Clustering detection
    within_1_std = sum(1 for v in values if abs(v - mean) <= std)
    pct_within_1_std = (within_1_std / len(values)) * 100
    print(f"\n  📊 Values within ±1 std: {pct_within_1_std:.1f}%")

    if pct_within_1_std > 85:
        print(f"     ❌ HEAVY CLUSTERING at mean (need z-score normalization)")
    elif pct_within_1_std > 75:
        print(f"     ⚠️  MODERATE CLUSTERING at mean")

    print()

# Compare factors side by side
print(f"{'='*80}")
print("SUMMARY - Z-SCORE NORMALIZATION RECOMMENDATION")
print(f"{'='*80}\n")

cur.execute("""
    SELECT
        composite_score, momentum_score, value_score, quality_score,
        growth_score, positioning_score
    FROM stock_scores
    WHERE composite_score IS NOT NULL
    LIMIT 1000
""")

scores = cur.fetchall()

print("Factor                      | Clustering | Recommendation")
print("-" * 80)

for idx, (col_name, label) in enumerate(factors):
    values = np.array([float(score[idx]) for score in scores if score[idx] is not None])
    if len(values) > 0:
        mean = np.mean(values)
        std = np.std(values)
        cv = (std / mean * 100) if mean > 0 else 0

        if cv < 10:
            rec = "🔴 CRITICAL - Implement z-score"
        elif cv < 20:
            rec = "🟠 HIGH - Consider z-score"
        elif cv < 30:
            rec = "🟡 MEDIUM - Monitor"
        else:
            rec = "🟢 OK - Already well distributed"

        print(f"{label:27} | {cv:7.1f}% | {rec}")

print(f"\n{'='*80}\n")

cur.close()
conn.close()

print("\n✅ Analysis complete! Review recommendations above.\n")
