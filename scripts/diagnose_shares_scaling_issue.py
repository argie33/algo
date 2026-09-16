#!/usr/bin/env python3
"""Diagnose systemic shares_outstanding scaling issue.

Hypothesis: Our loader converts raw shares to thousands (e.g., 50M → 50,000)
but SEC's scale varies by filer, or we have an inconsistent unit conversion.

This script compares our values, SEC XBRL raw facts, and yfinance to identify
the pattern and determine if it's a loader bug vs legitimate reporting difference.
"""

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from utils.db import get_db_connection  # noqa: E402


def get_shares_divergences():
    """Get all shares_outstanding divergences marked as investigate_severe."""
    db = get_db_connection()
    cursor = db.cursor()

    # Get divergences for shares fields with ratio >= 10x
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
        WHERE (our_field LIKE '%shares_outstanding%' OR our_field LIKE '%shares_basic%' OR our_field LIKE '%shares_diluted%')
        AND divergent = true
        AND ratio >= 10
        ORDER BY ratio DESC
        LIMIT 50
    """)

    records = cursor.fetchall()

    cursor.close()
    db.close()

    return records


def analyze_scaling_pattern(records):
    """Analyze if there's a consistent scale factor pattern."""
    patterns = {}

    for symbol, _table, _field, fiscal_year, our_value, yfinance_value, ratio in records:
        if not our_value or not yfinance_value:
            continue

        our_num = float(our_value)
        yf_num = float(yfinance_value)

        # Try to identify scaling patterns
        # Common scales: raw, thousands, millions
        scales = []

        if our_num > 0 and yf_num > 0:
            # If our value is ~1000x larger, we might be in raw, yf in thousands
            if our_num / yf_num >= 900 and our_num / yf_num <= 1100:
                scales.append("our_raw_yf_thousands")

            # If our value is ~1M larger, we might be in raw, yf in millions
            if our_num / yf_num >= 900_000 and our_num / yf_num <= 1_100_000:
                scales.append("our_raw_yf_millions")

            # If our value is ~1000x smaller, we might be in thousands, yf in raw
            if yf_num / our_num >= 900 and yf_num / our_num <= 1100:
                scales.append("our_thousands_yf_raw")

            # Check for exact power-of-10 relationships
            for power in range(1, 7):
                factor = 10**power
                if our_num / yf_num >= factor * 0.99 and our_num / yf_num <= factor * 1.01:
                    scales.append(f"our_yf_factor_{factor}x")

        # Store pattern
        pattern_key = tuple(sorted(scales)) if scales else ("no_pattern",)
        if pattern_key not in patterns:
            patterns[pattern_key] = []
        patterns[pattern_key].append((symbol, fiscal_year, our_num, yf_num, ratio))

    return patterns


def main():
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=50, help="Limit records to examine")
    _args = parser.parse_args()

    print("=" * 80)
    print("SHARES_OUTSTANDING SCALING ISSUE DIAGNOSIS")
    print("=" * 80)
    print()

    records = get_shares_divergences()

    print(f"Found {len(records)} shares_outstanding divergences with ratio >= 10x")
    print()

    if not records:
        print("No divergences found!")
        return

    patterns = analyze_scaling_pattern(records)

    print("SCALING PATTERNS DETECTED:")
    print()

    for pattern, cases in sorted(patterns.items(), key=lambda x: -len(x[1])):
        print(f"{pattern}: {len(cases)} cases")
        print("  Sample cases:")
        for symbol, fiscal_year, our_val, yf_val, ratio in cases[:3]:
            print(f"    {symbol} FY{fiscal_year}: our={our_val:>15.0f}  yfinance={yf_val:>15.0f}  ratio={ratio:.0f}x")
        print()

    # Specific recommendations
    print("DIAGNOSIS RECOMMENDATIONS:")
    print()

    if ("our_raw_yf_thousands",) in patterns:
        print("FINDING: Consistent 1000x scaling pattern suggests:")
        print("  Our loader stores raw share counts")
        print("  yfinance stores shares in thousands")
        print("  ACTION: Need to verify this is intentional design or a bug")
        print("          Check load_financial_statements.py for shares unit conversion")

    print()
    print("NEXT STEPS:")
    print("1. Check load_financial_statements.py for shares unit handling")
    print("2. Verify SEC XBRL scale attributes for these specific filings")
    print("3. Determine if our thousands-conversion is intentional or bug")
    print("4. If bug: fix loader, re-run comprehensive recovery")
    print("5. If intentional: document why we diverge from yfinance baseline")


if __name__ == "__main__":
    main()
