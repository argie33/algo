#!/usr/bin/env python3
"""Clean up NaN values in financial data tables.

This script fixes data integrity violations where NaN (Not-a-Number) was
stored in numeric columns. NaN should never be persisted to the database;
it indicates missing/invalid data that should be NULL.

Run: python3 scripts/cleanup_nan_data.py
"""

import sys

from utils.db import DatabaseContext


def cleanup_nan(table: str, columns: list[str]) -> int:
    """Replace NaN with NULL in specified table/columns."""
    updated = 0
    with DatabaseContext("write") as cur:
        for col in columns:
            # Use PostgreSQL's :: cast to text to detect 'NaN'
            cur.execute(f"""
                UPDATE {table}
                SET {col} = NULL
                WHERE {col}::text = 'NaN'
            """)
            updated += cur.rowcount
            if cur.rowcount > 0:
                print(f"  {table}.{col}: {cur.rowcount} NaN -> NULL")
    return updated

def main() -> int:
    print("Cleaning NaN data violations...")
    total = 0

    # Clean financial statements
    print("\n[Financial Statements]")
    total += cleanup_nan("annual_income_statement", ["revenue", "operating_income", "net_income", "earnings_per_share"])
    total += cleanup_nan("quarterly_income_statement", ["revenue", "operating_income", "net_income", "earnings_per_share"])
    total += cleanup_nan("annual_balance_sheet", ["stockholders_equity", "total_liabilities"])
    total += cleanup_nan("quarterly_balance_sheet", ["stockholders_equity", "total_liabilities"])
    total += cleanup_nan("annual_cash_flow", ["operating_cash_flow"])
    total += cleanup_nan("quarterly_cash_flow", ["operating_cash_flow"])

    # Clean metrics (these will cascade fixes from above)
    print("\n[Quality/Growth/Value Metrics]")
    total += cleanup_nan("quality_metrics", ["roe", "roa", "operating_margin", "net_margin", "debt_to_equity", "quality_score"])
    total += cleanup_nan("growth_metrics", ["revenue_growth_1y", "revenue_growth_3y", "revenue_growth_5y", "eps_growth_1y", "eps_growth_3y", "eps_growth_5y"])
    total += cleanup_nan("value_metrics", ["pe_ratio", "pb_ratio", "ps_ratio", "peg_ratio", "dividend_yield", "fcf_yield", "market_cap"])

    print(f"\nTotal NaN->NULL conversions: {total}")
    print("\nNote: Quality/growth scores may need recalculation after upstream data fixes.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
