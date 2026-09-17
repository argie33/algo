#!/usr/bin/env python3
"""Categorize all remaining 281 divergences by likely root cause for targeted remediation."""

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from utils.db import get_db_connection  # noqa: E402


def categorize_by_cause(
    symbol: str,
    field: str,
    fiscal_year: int,
    our_value: Any,
    yfinance_value: Any,
    ratio: float,
) -> str:
    """Determine root cause category for each divergence."""
    if not our_value or not yfinance_value:
        return "missing_data"

    yf_num = float(yfinance_value)

    # Check 1: Extreme scale errors (>1000x ratio)
    if ratio > 1000:
        # Check if it's consistent with a power-of-10 scale error
        if 900 < ratio < 1100:
            return "scale_error_1000x"
        elif 9000 < ratio < 11000:
            return "scale_error_10000x"
        else:
            return "extreme_divergence_unknown_cause"

    # Check 2: Negative values where they shouldn't be
    if field in ["revenue", "cost_of_revenue", "total_assets", "cash_and_equivalents"]:
        if yf_num < 0:
            return "yfinance_negative_value_garbage"

    # Check 3: Field-specific patterns
    if field in ["depreciation_expense", "capex", "cost_of_revenue", "revenue"]:
        if ratio > 100:
            return "likely_scale_or_unit_error"

    if field in ["operating_income", "net_income", "interest_expense"]:
        if ratio > 50:
            return "likely_reporting_timing_difference"

    if field in ["long_term_debt", "total_liabilities", "stockholders_equity"]:
        if ratio > 100:
            return "likely_balance_sheet_consolidation_scope"

    if field in ["earnings_per_share", "diluted_eps"]:
        if ratio > 50:
            return "likely_split_or_rounding_methodology"

    # Check 4: Moderate divergences without obvious cause
    if ratio > 10:
        return "investigate_moderate_unknown_cause"

    return "unknown_cause"


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", default="/tmp/remaining_divergence_categorization.json", help="Output categorization JSON"
    )
    args = parser.parse_args()

    db = get_db_connection()
    cursor = db.cursor()

    # Get ALL remaining investigate_severe records
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
        AND ratio >= 10
        AND our_field NOT LIKE '%shares%'
        ORDER BY ratio DESC
    """)

    records = cursor.fetchall()
    cursor.close()
    db.close()

    # Categorize each record
    categorized = defaultdict(list)
    for symbol, table, field, fiscal_year, our_value, yfinance_value, ratio in records:
        cause = categorize_by_cause(symbol, field, fiscal_year, our_value, yfinance_value, ratio)
        categorized[cause].append(
            {
                "symbol": symbol,
                "table": table,
                "field": field,
                "fiscal_year": fiscal_year,
                "our_value": str(our_value),
                "yfinance_value": yfinance_value,
                "ratio": float(ratio),
                "root_cause": cause,
            }
        )

    print("=" * 80)
    print("REMAINING 281 DIVERGENCES - ROOT CAUSE CATEGORIZATION")
    print("=" * 80)
    print()

    # Print summary
    print("CATEGORY BREAKDOWN:")
    print()
    for cause in sorted(categorized.keys(), key=lambda c: -len(categorized[c])):
        count = len(categorized[cause])
        avg_ratio = sum(r["ratio"] for r in categorized[cause]) / count
        print(f"{cause:50} {count:3} records (avg ratio: {avg_ratio:>8.1f}x)")

    print()
    print("REMEDIATION STRATEGY:")
    print()

    strategies = {
        "scale_error_1000x": "SEC verification + manual fix (1000x scale error detected)",
        "scale_error_10000x": "SEC verification + manual fix (10000x scale error detected)",
        "extreme_divergence_unknown_cause": "Priority: Manual SEC investigation required",
        "yfinance_negative_value_garbage": "Reject yfinance value, use SEC as-is",
        "likely_scale_or_unit_error": "SEC verification + manual fix if confirmed",
        "likely_reporting_timing_difference": "Document as legitimate reporting difference",
        "likely_balance_sheet_consolidation_scope": "Investigate consolidation scope differences",
        "likely_split_or_rounding_methodology": "Validate against split history (algo-d2's pattern)",
        "investigate_moderate_unknown_cause": "Individual root-cause investigation required",
        "missing_data": "Accept NULL if data unavailable in both sources",
        "unknown_cause": "Flag for manual review",
    }

    for cause, strategy in sorted(strategies.items()):
        if cause in categorized:
            count = len(categorized[cause])
            print(f"\n{cause}:")
            print(f"  Count: {count}")
            print(f"  Action: {strategy}")
            # Show top example
            top = sorted(categorized[cause], key=lambda x: -x["ratio"])[0]
            print(f"  Example: {top['symbol']} FY{top['fiscal_year']} {top['field']} ratio={top['ratio']:.0f}x")

    # Save to file
    output = {
        "total_remaining": len(records),
        "categories": {cause: len(categorized[cause]) for cause in categorized.keys()},
        "detailed_records": {cause: categorized[cause] for cause in sorted(categorized.keys())},
    }

    with open(args.output, "w") as f:
        json.dump(output, f, indent=2, default=str)

    print(f"\n\nDetailed categorization saved to: {args.output}")


if __name__ == "__main__":
    main()
