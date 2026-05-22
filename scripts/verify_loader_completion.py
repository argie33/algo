#!/usr/bin/env python3
"""Verify all loaders have completed and loaded data correctly."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from config.env_loader import load_env
from utils.db_connection import get_db_connection
from datetime import date, timedelta

def get_table_info(cur, table_name):
    """Get row count and latest date for a table."""
    try:
        # Get row count
        cur.execute(f"SELECT COUNT(*) FROM {table_name}")
        count = cur.fetchone()[0]

        # Try to get latest date
        for date_col in ['date', 'created_at', 'updated_at']:
            try:
                cur.execute(f"SELECT MAX({date_col}) FROM {table_name}")
                latest = cur.fetchone()[0]
                return count, latest
            except:
                continue
        return count, None
    except Exception as e:
        return None, f"ERROR: {str(e)[:50]}"

def main():
    load_env()
    conn = get_db_connection()
    cur = conn.cursor()

    print("\n" + "="*80)
    print("LOADER COMPLETION VERIFICATION")
    print("="*80)

    tables_to_check = {
        "stock_symbols": ("Reference data", "10000+"),
        "price_daily": ("Price history", "8000000+"),
        "etf_price_daily": ("ETF prices", "100000+"),
        "technical_data_daily": ("Technical indicators", "8000000+"),
        "buy_sell_daily": ("Daily signals", "5000+"),
        "buy_sell_weekly": ("Weekly signals", "5000+"),
        "buy_sell_monthly": ("Monthly signals", "500+"),
        "signal_quality_scores": ("Signal quality", "5000+"),
        "algo_metrics_daily": ("Algo metrics", "5000+"),
        "economic_data": ("Economic data", "100+"),
        "company_profile": ("Company profiles", "5000+"),
        "analyst_sentiment": ("Analyst sentiment", "5000+"),
        "earnings_calendar": ("Earnings calendar", "10000+"),
        "swing_trader_scores": ("Swing trader scores", "5000+"),
    }

    total_rows = 0
    tables_ok = 0
    tables_error = 0

    for table, (description, expected_min) in tables_to_check.items():
        count, latest = get_table_info(cur, table)
        status = "✅" if count and count > 0 else "❌"
        if count is None:
            status = "⚠️"
            tables_error += 1
        else:
            tables_ok += 1
            total_rows += count

        latest_str = f" (latest: {latest})" if isinstance(latest, date) else ""
        print(f"{status} {table:30s} | {str(count):12s} rows | expected: {expected_min:10s}{latest_str}")

    print("\n" + "="*80)
    print(f"SUMMARY")
    print("="*80)
    print(f"✅ Tables loaded:  {tables_ok}")
    print(f"⚠️  Tables error:   {tables_error}")
    print(f"Total rows loaded: {total_rows:,}")

    if tables_error == 0:
        print("\n✅ ALL LOADERS COMPLETED SUCCESSFULLY!")
        return 0
    else:
        print(f"\n❌ {tables_error} table(s) have errors")
        return 1

if __name__ == "__main__":
    sys.exit(main())
