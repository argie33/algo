#!/usr/bin/env python3
"""Analyze score reload results and identify remaining data gaps."""

import json
import subprocess


def get_scores_data():
    """Fetch current scores via API."""
    result = subprocess.run(["curl", "-s", "http://localhost:3001/api/scores/coverage"], capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error fetching API: {result.stderr}")
        return None
    return json.loads(result.stdout)


def analyze_gaps(data):
    """Analyze what data is still missing and blocking scores."""
    if not data or "data" not in data:
        print("No data returned from API")
        return

    resp = data["data"]
    summary = resp.get("summary", {})
    factors = resp.get("factors", [])

    print("\n" + "=" * 80)
    print("SCORES RELOAD ANALYSIS")
    print("=" * 80)

    # Overview
    print("\nOVERVIEW:")
    print(f"  Active Universe: {summary.get('universe_estimate', 'N/A'):,} stocks")
    print(f"  Total Factors: {summary.get('factor_count', 'N/A')}")

    # Category totals
    print("\nDATA GAPS BY CATEGORY:")
    categories = summary.get("category_totals", {})
    for cat in summary.get("category_order", []):
        count = categories.get(cat, 0)
        if count > 0:
            pct = (count / summary.get("universe_estimate", 1)) * 100
            print(f"  • {cat}: {count:,} ({pct:.1f}%)")

    # Biggest blocking factors (most symbols missing)
    print("\nTOP 10 FACTORS BLOCKING MOST SYMBOLS:")
    sorted_factors = sorted(factors, key=lambda x: x.get("total_missing", 0), reverse=True)[:10]
    for i, factor in enumerate(sorted_factors, 1):
        missing = factor.get("total_missing", 0)
        pct = factor.get("pct_missing", 0)
        print(f"  {i:2}. {factor.get('factor', 'unknown'):35} {missing:5,} symbols ({pct:.1f}%)")

    # Factors with highest "real" missing data (not legitimate/n/a)
    print("\nTOP FACTORS WITH REAL DATA GAPS (excluding legitimate/n/a):")
    real_gaps = {}
    for factor in factors:
        total_missing = 0
        reasons = factor.get("reasons", [])
        for reason in reasons:
            cat = reason.get("category", "")
            if cat not in ["Legitimate / not applicable"]:
                total_missing += reason.get("count", 0)
        if total_missing > 0:
            real_gaps[factor.get("factor", "")] = {
                "count": total_missing,
                "pct": (total_missing / summary.get("universe_estimate", 1)) * 100,
            }

    sorted_real = sorted(real_gaps.items(), key=lambda x: x[1]["count"], reverse=True)[:10]
    for i, (factor, gap) in enumerate(sorted_real, 1):
        print(f"  {i:2}. {factor:35} {gap['count']:5,} symbols ({gap['pct']:.1f}%)")

    # Data sources used
    print("\nTOP DATA SOURCES:")
    sources = summary.get("source_totals", {})
    sorted_sources = sorted(sources.items(), key=lambda x: x[1], reverse=True)[:8]
    for source, count in sorted_sources:
        print(f"  • {source:45} {count:6,}")

    print(f"\n{'=' * 80}\n")


if __name__ == "__main__":
    data = get_scores_data()
    analyze_gaps(data)
