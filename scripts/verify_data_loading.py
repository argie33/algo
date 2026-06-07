#!/usr/bin/env python3
"""Comprehensive data loading and algorithm verification."""
import sys
import os
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from datetime import datetime, timezone
from utils.database_context import DatabaseContext
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def check_data_freshness():
    """Check if all critical data is fresh and up-to-date."""
    print("\n" + "="*70)
    print("DATA FRESHNESS CHECK")
    print("="*70)

    critical_tables = [
        ('price_daily', 'date', False),
        ('etf_price_daily', 'date', False),
        ('market_health_daily', 'date', True),
        ('trend_template_data', 'date', True),
        ('technical_data_daily', 'date', False),
        ('buy_sell_daily', 'date', False),
        ('signal_quality_scores', 'date', False),
        ('swing_trader_scores', 'date', False),
    ]

    today = datetime.now().date()
    results = {}

    try:
        with DatabaseContext('read') as cur:
            print(f"\nToday's date: {today}\n")
            print(f"{'Table Name':<30} {'Row Count':>12} {'Latest Date':>15} {'Age (days)':>12}")
            print("-"*70)

            for table, date_col, needs_cast in critical_tables:
                try:
                    date_expr = f"CAST({date_col} AS DATE)" if needs_cast else date_col
                    cur.execute(f"SELECT COUNT(*), MAX({date_expr}) FROM {table}")
                    count, max_date = cur.fetchone()
                    if count == 0:
                        print(f"{table:<30} {'EMPTY':<12} {'(no data)':<15} {'-':>12}")
                        results[table] = {'status': 'EMPTY', 'age': None}
                    elif max_date:
                        age = (today - max_date).days
                        status = "[FRESH]" if age <= 1 else f"[STALE] ({age}d old)"
                        print(f"{table:<30} {count:>12,} {str(max_date):>15} {age:>12}")
                        results[table] = {'status': status, 'age': age, 'count': count}
                    else:
                        print(f"{table:<30} {'ERROR':<12} {'(null max)':<15} {'-':>12}")
                        results[table] = {'status': 'ERROR', 'age': None}
                except Exception as e:
                    print(f"{table:<30} {'ERROR':<12} {str(e)[:30]:<15} {'-':>12}")
                    results[table] = {'status': 'ERROR', 'error': str(e)}

    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        return False

    return results

def check_loader_status():
    """Check data_loader_status to see which loaders have run recently."""
    print("\n" + "="*70)
    print("LOADER STATUS")
    print("="*70)

    try:
        with DatabaseContext('read') as cur:
            cur.execute("""
                SELECT table_name, status, age_days, completion_pct, last_updated
                FROM data_loader_status
                ORDER BY last_updated DESC NULLS LAST
                LIMIT 15
            """)
            results = cur.fetchall()

            if not results:
                print("No loader status records found.")
                return False

            print(f"\n{'Loader Name':<30} {'Status':<12} {'Age':<6} {'Progress':<10} {'Last Updated':<20}")
            print("-"*80)
            for row in results:
                table_name, status, age_days, completion_pct, last_updated = row
                age_str = f"{age_days}d" if age_days else "?"
                pct_str = f"{int(completion_pct or 0)}%" if completion_pct else "?"
                time_str = last_updated.strftime("%Y-%m-%d %H:%M") if last_updated else "never"
                print(f"{table_name:<30} {status:<12} {age_str:<6} {pct_str:<10} {time_str:<20}")

            return True

    except Exception as e:
        logger.error(f"Failed to check loader status: {e}")
        return False

def check_halt_flag():
    """Check if orchestrator halt flag is set."""
    print("\n" + "="*70)
    print("ORCHESTRATOR HALT FLAG & CONFIG")
    print("="*70)

    try:
        with DatabaseContext('read') as cur:
            cur.execute("""
                SELECT key, value, updated_at
                FROM algo_config
                WHERE key IN ('halt_flag', 'halt_reason', 'trading_mode', 'execution_mode', 'paper_trading_enabled')
                ORDER BY updated_at DESC
            """)
            results = cur.fetchall()

            if not results:
                print("No config records found.")
                return None

            print(f"\n{'Key':<30} {'Value':<40} {'Updated':<20}")
            print("-"*90)

            halt_status = None
            for key, value, updated_at in results:
                if key == 'halt_flag':
                    halt_status = value
                    status_icon = "[HALTED]" if value == 'true' else "[RUNNING]"
                    print(f"{key:<30} {status_icon:<40} {str(updated_at):<20}")
                else:
                    print(f"{key:<30} {str(value):<40} {str(updated_at):<20}")

            return halt_status

    except Exception as e:
        logger.error(f"Failed to check halt flag: {e}")
        return None

def main():
    """Run all verification checks."""
    print("\nCOMPREHENSIVE DATA LOADING & ALGORITHM VERIFICATION\n")

    try:
        with DatabaseContext('read') as cur:
            cur.execute("SELECT NOW()")
            db_time = cur.fetchone()[0]
            logger.info(f"[OK] Database connected. DB Time: {db_time}")
    except Exception as e:
        logger.error(f"[ERROR] Database connection failed: {e}")
        sys.exit(1)

    freshness = check_data_freshness()
    loader_status = check_loader_status()
    halt_flag = check_halt_flag()

    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)

    if freshness:
        stale_tables = [t for t, r in freshness.items() if r.get('age') and r['age'] > 1]
        if stale_tables:
            print(f"[WARNING] {len(stale_tables)} tables stale (>1 day): {', '.join(stale_tables)}")
        else:
            print("[OK] All critical data tables are fresh")

    if halt_flag == 'true':
        print("[HALT] HALT FLAG SET - Orchestrator will not generate signals")
    else:
        print("[OK] Halt flag not set - Orchestrator can execute")

    print("\n[OK] Verification complete!\n")

if __name__ == '__main__':
    main()
