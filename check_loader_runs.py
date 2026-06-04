#!/usr/bin/env python3
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from utils.database_context import DatabaseContext
from datetime import datetime, timedelta

print("\nChecking recent loader runs...\n")
print("="*80)

try:
    with DatabaseContext('read') as cur:
        # Get loader status for critical loaders
        critical_loaders = [
            'stock_prices_daily',
            'technical_data_daily',
            'market_health_daily',
            'trend_template_data',
            'buy_sell_daily',
            'signal_quality_scores',
            'swing_trader_scores',
            'sector_ranking',
            'algo_metrics_daily'
        ]

        print("CRITICAL LOADERS STATUS (EOD Pipeline)")
        print("="*80)

        for loader in critical_loaders:
            try:
                cur.execute("""
                    SELECT latest_date, status, error_message, last_updated
                    FROM data_loader_status
                    WHERE table_name = %s
                """, (loader,))

                row = cur.fetchone()
                if row:
                    latest_date, status, error_msg, last_updated = row

                    # Calculate age
                    if last_updated:
                        age = datetime.utcnow() - last_updated
                        age_str = f"{age.total_seconds()/3600:.1f}h ago"
                    else:
                        age_str = "unknown"

                    status_icon = "[OK]" if status == "success" else "[FAIL]"
                    print(f"{status_icon} {loader:30s} | {latest_date} | {status:10s} | {age_str}")

                    if error_msg:
                        print(f"     ERROR: {error_msg[:70]}")
                else:
                    print(f"[--] {loader:30s} | No status recorded")
            except Exception as e:
                print(f"[!!] {loader:30s} | {str(e)[:70]}")

        print("\n" + "="*80)
        print("ORCHESTRATOR STATUS")
        print("="*80)

        # Check orchestrator runs
        cur.execute("""
            SELECT phase, status, error_message, run_date
            FROM orchestrator_phase_results
            ORDER BY run_id DESC, phase ASC
            LIMIT 20
        """)

        rows = cur.fetchall()
        if rows:
            print("\nRecent orchestrator phases:")
            last_run = None
            for phase, status, error_msg, run_date in rows:
                if run_date != last_run:
                    print(f"\n  Run {run_date}:")
                    last_run = run_date

                status_icon = "[OK]" if status == "success" else "[HALT]" if status == "halt" else "[WARN]"
                print(f"    {status_icon} Phase {phase}: {status}")

                if error_msg:
                    print(f"        -> {error_msg[:60]}")
        else:
            print("No orchestrator phase results found")

except Exception as e:
    print(f"Database error: {e}")

print("\n" + "="*80)
