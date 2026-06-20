#!/usr/bin/env python3
"""Investigate sparse technical data on 2026-06-18.

Queries database to find root cause of sparse data (52 symbols vs normal 8000+).
Compares 2026-06-18 (Thursday before Juneteenth) with nearby dates.
"""

import logging
from datetime import date, timedelta

from utils.db.context import DatabaseContext


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def investigate_sparse_data():
    """Investigate sparse technical data on specific date."""

    target_date = date(2026, 6, 18)  # Thursday (sparse data reported)
    dates_to_check = [
        target_date - timedelta(days=2),  # Tuesday (2 days before)
        target_date - timedelta(days=1),  # Wednesday (1 day before)
        target_date,                      # Thursday (sparse data)
        target_date + timedelta(days=1),  # Friday (Juneteenth)
        target_date + timedelta(days=3),  # Monday (after weekend)
    ]

    print("\n" + "="*80)
    print("INVESTIGATION: Sparse Technical Data on 2026-06-18")
    print("="*80)

    print("\n[1/3] Price Data Coverage by Date")
    print("-" * 80)
    print(f"{'Date':<12} {'Symbols':<10} {'Rows':<10} {'Avg/Symbol':<12} {'Status':<30}")
    print("-" * 80)

    with DatabaseContext("read") as cur:
        for check_date in dates_to_check:
            # Check price_daily coverage
            cur.execute(
                """
                SELECT
                    COUNT(DISTINCT symbol) as symbol_count,
                    COUNT(*) as row_count
                FROM price_daily
                WHERE date = %s
                """,
                [check_date],
            )
            result = cur.fetchone()
            symbols, rows = result[0], result[1]
            avg_per_symbol = rows / symbols if symbols > 0 else 0

            status = "OK" if symbols > 7000 else "⚠️  SPARSE" if symbols > 100 else "❌ CRITICAL"
            print(
                f"{check_date!s:<12} {symbols:<10} {rows:<10} {avg_per_symbol:<12.1f} {status:<30}"
            )

    print("\n[2/3] Technical Data Coverage by Date")
    print("-" * 80)
    print(f"{'Date':<12} {'Symbols':<10} {'Rows':<10} {'Avg/Symbol':<12} {'Status':<30}")
    print("-" * 80)

    with DatabaseContext("read") as cur:
        for check_date in dates_to_check:
            # Check technical_data_daily coverage
            cur.execute(
                """
                SELECT
                    COUNT(DISTINCT symbol) as symbol_count,
                    COUNT(*) as row_count
                FROM technical_data_daily
                WHERE date = %s
                """,
                [check_date],
            )
            result = cur.fetchone()
            symbols, rows = result[0], result[1]
            avg_per_symbol = rows / symbols if symbols > 0 else 0

            status = "OK" if symbols > 7000 else "⚠️  SPARSE" if symbols > 100 else "❌ CRITICAL"
            print(
                f"{check_date!s:<12} {symbols:<10} {rows:<10} {avg_per_symbol:<12.1f} {status:<30}"
            )

    print("\n[3/3] Root Cause Analysis")
    print("-" * 80)

    with DatabaseContext("read") as cur:
        # Get detailed stats for 2026-06-18
        cur.execute(
            """
            SELECT
                symbol,
                COUNT(*) as price_rows,
                MIN(date) as first_date,
                MAX(date) as last_date,
                MIN(CASE WHEN close IS NULL THEN 1 ELSE 0 END) as has_nulls
            FROM price_daily
            WHERE date = %s
            GROUP BY symbol
            ORDER BY price_rows DESC
            LIMIT 20
            """,
            [target_date],
        )

        prices_2026_06_18 = cur.fetchall()

        if prices_2026_06_18:
            print("\nTop 20 symbols with price data on 2026-06-18:")
            print(f"{'Symbol':<8} {'Rows':<6} {'First':<12} {'Last':<12} {'Has Nulls':<12}")
            print("-" * 50)
            for row in prices_2026_06_18:
                symbol, rows, first_date, last_date, has_nulls = row
                print(f"{symbol:<8} {rows:<6} {first_date!s:<12} {last_date!s:<12} {'Yes' if has_nulls else 'No':<12}")
        else:
            print("❌ NO price data found for 2026-06-18!")

        # Check if there's a gap in dates
        print("\nChecking for date gaps around 2026-06-18:")
        cur.execute(
            """
            SELECT DISTINCT date
            FROM price_daily
            WHERE date BETWEEN %s AND %s
            ORDER BY date DESC
            LIMIT 10
            """,
            [target_date - timedelta(days=5), target_date + timedelta(days=5)],
        )

        dates = cur.fetchall()
        for (d,) in dates:
            marker = "  ← SPARSE DATA DATE" if d == target_date else ""
            print(f"  {d}{marker}")

    print("\n[SUMMARY]")
    print("-" * 80)
    print("Possible root causes for sparse technical data on 2026-06-18:")
    print("1. Early market close or holiday (Juneteenth observed on 6/19)")
    print("2. Incomplete price data from upstream loader (stock_prices_daily failed)")
    print("3. Technical loader encountered error on that date")
    print("4. Data corruption or missing data in database")
    print("\nNext steps:")
    print("1. Check Step Functions execution logs for technical_data_daily_vectorized on 2026-06-18")
    print("2. If price data is sparse too: Issue is upstream (stock_prices_daily loader)")
    print("3. If price data is complete but technical data sparse: Issue in technical indicator computation")
    print("4. If both are sparse: Likely market closure or data not loaded for that date")
    print("="*80 + "\n")


if __name__ == "__main__":
    investigate_sparse_data()
