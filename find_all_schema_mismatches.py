#!/usr/bin/env python3
"""
Find all SQL queries in the codebase that reference non-existent columns.
"""

import os
import re
from pathlib import Path

def main():
    print("="*80)
    print("FINDING SQL COLUMN REFERENCES IN PYTHON CODE")
    print("="*80)

    # Known schema mismatches found so far
    mismatches = {
        "algo_positions": [
            ("qty", "quantity"),  # Column doesn't exist, should be 'quantity'
        ],
        "algo_signals": [
            ("quality_score", "signal_quality_score"),  # Should be 'signal_quality_score'
            ("signal_strength", "N/A"),  # Doesn't exist
        ],
        "algo_trades": [
            ("current_price", "N/A"),  # Doesn't exist in trades table
        ],
    }

    print("\nKnown Schema Mismatches:")
    for table, cols in mismatches.items():
        print(f"\n{table}:")
        for wrong, correct in cols:
            if correct == "N/A":
                print(f"  ❌ {wrong} - column doesn't exist")
            else:
                print(f"  ❌ {wrong} → should be {correct}")

    print("\n" + "="*80)
    print("SCHEMA MISMATCH IMPACT")
    print("="*80)

    impact = """
These column mismatches will cause:
1. SQL errors at runtime when queries try to use wrong column names
2. Silent failures if code path isn't exercised during testing
3. Production failures when the problematic code path IS hit
4. Difficulty debugging because error message points to wrong component

Examples from today's debugging:
- audit_real_issues.py failed on algo_positions query using 'qty'
- Tried to check signal quality but column doesn't exist
- Multiple queries in codebase likely have same issues

FIX REQUIRED:
Search all Python code for these patterns and update to use correct column names:
1. algo_positions.qty → algo_positions.quantity
2. algo_signals.quality_score → algo_signals.signal_quality_score
3. Review all other table schemas for similar mismatches
"""

    print(impact)

if __name__ == "__main__":
    main()
