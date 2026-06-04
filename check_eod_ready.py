#!/usr/bin/env python3
"""Check if EOD pipeline is ready to run successfully."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from utils.database_context import DatabaseContext
from datetime import datetime, date, timedelta

print("\n" + "="*80)
print("EOD PIPELINE READINESS CHECK")
print("="*80 + "\n")

critical_tables = {
    'stock_symbols': ('symbol', None),
    'price_daily': ('symbol', 'date'),
    'market_health_daily': (None, 'date'),
    'technical_data_daily': ('symbol', 'date'),
    'trend_template_data': ('symbol', 'date'),
    'buy_sell_daily': ('symbol', 'date'),
    'signal_quality_scores': ('symbol', 'date'),
    'swing_trader_scores': ('symbol', 'date'),
    'sector_ranking': ('sector_name', 'date'),
    'algo_metrics_daily': (None, 'date'),
}

try:
    with DatabaseContext('read') as cur:
        print("Table Data Status:")
        print("-" * 80)

        all_ready = True
        for table, (pk_col, date_col) in critical_tables.items():
            try:
                if date_col:
                    cur.execute(f"SELECT COUNT(*), MAX({date_col}) FROM {table}")
                else:
                    cur.execute(f"SELECT COUNT(*), NULL FROM {table}")

                row = cur.fetchone()
                count = row[0] if row else 0
                max_date = row[1] if row and len(row) > 1 else None

                if max_date:
                    age_days = (date.today() - max_date).days
                    status = "OK" if age_days <= 1 else f"STALE ({age_days}d)"
                    if age_days > 1:
                        all_ready = False
                else:
                    status = "EMPTY" if count == 0 else "NO DATE"
                    if count == 0:
                        all_ready = False

                print(f"  {table:30s} | {count:10,} rows | {status:15s} | {max_date}")

            except Exception as e:
                print(f"  {table:30s} | ERROR: {str(e)[:50]}")
                all_ready = False

        print("\n" + "-" * 80)

        if all_ready:
            print("STATUS: [OK] All critical tables are ready for EOD pipeline\n")
        else:
            print("STATUS: [WARN] Some tables may need updating\n")

        # Check specific things that would block the pipeline
        print("\nDATA FRESHNESS CHECKS (for Phase 1 data freshness):")
        print("-" * 80)

        required_fresh = {
            'price_daily': 'SPY price data',
            'market_health_daily': 'Market health',
            'trend_template_data': 'Trend template data',
        }

        for table, description in required_fresh.items():
            cur.execute(f"SELECT MAX(date) FROM {table}")
            row = cur.fetchone()
            max_date = row[0] if row else None

            if max_date:
                age = (date.today() - max_date).days
                if age <= 1:
                    status = "[OK]"
                elif age <= 5:
                    status = "[WARN]"
                else:
                    status = "[FAIL]"
                print(f"  {status} {description:30s} | {max_date} ({age}d old)")
            else:
                print(f"  [FAIL] {description:30s} | MISSING")

        print("\n" + "-" * 80)
        print("\nMIGRATION STATUS:")
        print("-" * 80)

        # Check sector_ranking schema specifically
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name='sector_ranking'
            AND column_name IN ('date', 'date_recorded')
        """)

        sector_cols = [r[0] for r in cur.fetchall()]

        if 'date' in sector_cols:
            print("  [OK] sector_ranking has 'date' column (Migration 015 applied)")
        else:
            print("  [FAIL] sector_ranking missing 'date' column (Migration 015 NOT applied)")

        if 'date_recorded' in sector_cols:
            print("  [WARN] sector_ranking still has 'date_recorded' (cleanup needed)")

        print("\n" + "="*80)

except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
