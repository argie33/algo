#!/usr/bin/env python3
"""Monitor loader SLA compliance and morning prep pipeline timing.

Tracks whether loaders complete within their SLAs to ensure algo runs have fresh data.
"""
import sys
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.database_context import DatabaseContext

ET = ZoneInfo("America/New_York")

def monitor_current_status():
    """Show current loader and data freshness status."""
    try:
        with DatabaseContext('read') as cur:
            print("\n" + "="*90)
            print("LOADER SLA COMPLIANCE - CURRENT STATUS")
            print("="*90 + "\n[MORNING PREP PIPELINE: 2:00 AM - 9:30 AM ET]\n")

            cur.execute("""
                SELECT table_name, latest_date, CURRENT_DATE - latest_date as age_days, row_count, status
                FROM data_loader_status
                WHERE table_name IN ('price_daily', 'technical_data_daily', 'market_health_daily', 'swing_trader_scores')
                ORDER BY table_name
            """)

            for row in cur.fetchall():
                name, latest, age, rows, status = row.get('table_name'), row.get('latest_date'), row.get('age_days'), row.get('row_count'), row.get('status')
                age = age or 0
                fresh = "FRESH" if age <= 1 else "STALE"
                print(f"  {name:25} {str(latest):11} {age:3}d old  {rows or 0:9} rows  [{fresh}]")

            print("\n[RECENT ORCHESTRATOR RUNS]\n")
            cur.execute("""
                SELECT started_at AT TIME ZONE 'America/New_York', overall_status, EXTRACT(EPOCH FROM (completed_at - started_at))/60 as duration
                FROM orchestrator_execution_log
                WHERE run_date = CURRENT_DATE
                ORDER BY started_at DESC LIMIT 5
            """)

            success_count = 0
            total_count = 0
            for row in cur.fetchall():
                start = str(row[0] or '')[-8:]
                status = row[1]
                duration = row[2] or 0
                if status == 'success': success_count += 1
                total_count += 1
                print(f"  {start}  {status:8} {duration:6.1f}min")

            if total_count > 0:
                print(f"\nSuccess Rate: {success_count}/{total_count} = {100*success_count/total_count:.1f}%")

            return 0
    except Exception as e:
        print(f"Error: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(monitor_current_status())
