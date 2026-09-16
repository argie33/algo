#!/usr/bin/env python3
"""Generate comprehensive report on divergence recovery status and categorization.

This script produces a detailed breakdown of:
1. Which divergences are caused by yfinance garbage (won't fix)
2. Which divergences are SEC errors (need manual investigation)
3. Which divergences are legitimate reporting differences (document as-is)
4. Restoration validation metrics
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from utils.db import get_db_connection  # noqa: E402


def categorize_divergence(symbol, table, field, our_value, yfinance_value, ratio, fiscal_year):
    """Categorize why a divergence exists."""
    # Micro-cap threshold
    if field in ["shares_outstanding_basic", "shares_outstanding_diluted"]:
        if yfinance_value and float(yfinance_value) < 1000 and float(yfinance_value) > 0:
            return "YFINANCE_GARBAGE_MICROCAP"

    # Extreme ratio = likely corruption or yfinance garbage
    if ratio > 1000:
        return "EXTREME_DIVERGENCE_LIKELY_GARBAGE"
    elif ratio > 100:
        return "SEVERE_DIVERGENCE"
    elif ratio > 50:
        return "MODERATE_DIVERGENCE"
    elif ratio > 10:
        return "SIGNIFICANT_DIVERGENCE"
    else:
        return "MINOR_DIVERGENCE"


def analyze_divergences():
    """Analyze current divergence state and categorize them."""
    db = get_db_connection()
    cursor = db.cursor()

    cursor.execute("""
        SELECT DISTINCT
            symbol,
            our_table,
            our_field,
            fiscal_year,
            our_value,
            yfinance_value::text as yfinance_value,
            ratio
        FROM xbrl_yfinance_line_item_report
        WHERE divergent = true
        ORDER BY ratio DESC
    """)

    records = cursor.fetchall()

    categorized = defaultdict(list)
    for symbol, table, field, fiscal_year, our_value, yfinance_value, ratio in records:
        category = categorize_divergence(symbol, table, field, our_value, yfinance_value, ratio, fiscal_year)
        categorized[category].append(
            {
                "symbol": symbol,
                "table": table,
                "field": field,
                "fiscal_year": fiscal_year,
                "our_value": our_value,
                "yfinance_value": yfinance_value,
                "ratio": float(ratio),
            }
        )

    cursor.close()
    db.close()

    return categorized


def main():
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="/tmp/divergence_report.json", help="Output JSON report file")
    args = parser.parse_args()

    print("=" * 80)
    print("DIVERGENCE CATEGORIZATION & RECOVERY REPORT")
    print("=" * 80)
    print()

    categorized = analyze_divergences()

    # Summary
    total_divergences = sum(len(records) for records in categorized.values())
    print(f"Total divergences: {total_divergences}")
    print()

    # Category breakdown
    print("CATEGORY BREAKDOWN:")
    print()

    category_order = [
        "YFINANCE_GARBAGE_MICROCAP",
        "EXTREME_DIVERGENCE_LIKELY_GARBAGE",
        "SEVERE_DIVERGENCE",
        "MODERATE_DIVERGENCE",
        "SIGNIFICANT_DIVERGENCE",
        "MINOR_DIVERGENCE",
    ]

    for category in category_order:
        if category in categorized:
            records = categorized[category]
            print(f"{category}: {len(records)} records")

    print()
    print("CATEGORY MEANINGS:")
    print()
    print("YFINANCE_GARBAGE_MICROCAP: Yfinance returned tiny share counts (<1000)")
    print("  Action: Use SEC value (yfinance unreliable for micro-caps)")
    print()
    print("EXTREME_DIVERGENCE_LIKELY_GARBAGE: >1000x divergence (almost always corruption)")
    print("  Action: Verify against SEC filing, use SEC value")
    print()
    print("SEVERE_DIVERGENCE: 100-1000x divergence")
    print("  Action: Investigate root cause, validate proposed fix")
    print()
    print("MODERATE_DIVERGENCE: 50-100x divergence")
    print("  Action: Review carefully, check SEC filing, validate yfinance")
    print()
    print("SIGNIFICANT_DIVERGENCE: 10-50x divergence")
    print("  Action: Document root cause before fixing")
    print()
    print("MINOR_DIVERGENCE: <10x divergence")
    print("  Action: Often legitimate reporting differences, document as-is")
    print()

    # Save report
    report = {
        "total_divergences": total_divergences,
        "categories": {category: len(categorized.get(category, [])) for category in category_order},
        "sample_records": {
            category: categorized.get(category, [])[:3] for category in category_order if category in categorized
        },
    }

    with open(args.output, "w") as f:
        json.dump(report, f, indent=2, default=str)

    print(f"Full report saved to: {args.output}")


if __name__ == "__main__":
    main()
