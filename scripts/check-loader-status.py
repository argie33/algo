#!/usr/bin/env python3
"""Check loader status and report failures - MEDIUM ISSUE FIX.

Provides visibility into loader execution status to catch silent failures.
Queries data_loader_status table and reports:
- Loaders that are currently running (stuck?)
- Loaders that failed on last execution
- Loaders that are stale (not updated recently)
- Summary health check
"""
import sys
import os
from datetime import datetime, timedelta, date
from pathlib import Path

# Add parent dir to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.database_context import DatabaseContext
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")


def check_loader_status():
    """Check and report loader execution status."""
    try:
        with DatabaseContext('read') as cur:
            # Get all loader status records
            cur.execute("""
                SELECT
                    table_name,
                    status,
                    latest_date,
                    age_days,
                    last_updated,
                    error_message,
                    execution_started,
                    execution_completed,
                    frequency
                FROM data_loader_status
                ORDER BY table_name
            """)
            loaders = cur.fetchall() or []

            if not loaders:
                print("❌ No loader status records found. Loaders may not be reporting status.")
                return 1

            now = datetime.now(ET)
            issues = []
            running = []
            stale = []
            failed = []

            print("\n" + "=" * 80)
            print("LOADER STATUS REPORT")
            print("=" * 80)

            for loader in loaders:
                table_name = loader.get('table_name')
                status = loader.get('status', '').lower()
                latest_date = loader.get('latest_date')
                age_days = loader.get('age_days')
                error = loader.get('error_message')
                started = loader.get('execution_started')
                completed = loader.get('execution_completed')
                frequency = loader.get('frequency', 'unknown')
                last_updated = loader.get('last_updated')

                # Determine issue severity
                if status == 'running' and started:
                    # Check if running too long
                    runtime_hours = (now - started).total_seconds() / 3600
                    if runtime_hours > 2:  # More than 2 hours
                        running.append({
                            'table': table_name,
                            'started': started,
                            'runtime_hours': runtime_hours,
                            'reason': 'Stuck (running >2 hours)'
                        })
                        print(f"⚠️  {table_name:30} RUNNING (stuck >2h)")
                    else:
                        print(f"⏳ {table_name:30} RUNNING ({runtime_hours:.1f}h)")

                elif status == 'failed' or error:
                    failed.append({
                        'table': table_name,
                        'error': error,
                        'last_updated': last_updated
                    })
                    print(f"❌ {table_name:30} FAILED")
                    if error:
                        print(f"   Error: {error[:100]}")

                elif status == 'completed':
                    # Check staleness based on frequency
                    expected_max_age = {
                        'hourly': 1,      # Should have data from last hour
                        'daily': 1,       # Should have data from yesterday/today
                        'weekly': 7,
                        'monthly': 32,
                        'unknown': 3,     # Default: 3 days
                    }
                    max_age = expected_max_age.get(frequency.lower(), 3)

                    if age_days is not None and age_days > max_age:
                        stale.append({
                            'table': table_name,
                            'age_days': age_days,
                            'max_age': max_age,
                            'frequency': frequency
                        })
                        print(f"⚠️  {table_name:30} STALE ({age_days}d old, max {max_age}d for {frequency})")
                    else:
                        status_icon = "✅"
                        print(f"{status_icon} {table_name:30} OK (age={age_days or '?'}d, {latest_date or '?'})")
                else:
                    print(f"❓ {table_name:30} UNKNOWN STATUS: {status}")

            # Summary
            print("\n" + "=" * 80)
            print("SUMMARY")
            print("=" * 80)
            print(f"Total loaders: {len(loaders)}")
            print(f"  ✅ OK: {len(loaders) - len(running) - len(stale) - len(failed)}")
            print(f"  ⏳ Running: {len(running)}")
            if running:
                for r in running:
                    print(f"     - {r['table']} (started {r['started']}, {r['runtime_hours']:.1f}h)")
            print(f"  ⚠️  Stale: {len(stale)}")
            if stale:
                for s in stale:
                    print(f"     - {s['table']} ({s['age_days']}d old, max {s['max_age']}d)")
            print(f"  ❌ Failed: {len(failed)}")
            if failed:
                for f in failed:
                    print(f"     - {f['table']}: {f['error'][:80] if f['error'] else 'unknown error'}")

            # Exit code
            if failed or running:
                print("\n⚠️  ACTION REQUIRED: Fix failed or stuck loaders")
                return 1
            elif stale:
                print("\n⚠️  WARNING: Some loaders are stale but not failed")
                return 0  # Warning only
            else:
                print("\n✅ All loaders healthy")
                return 0

    except Exception as e:
        print(f"❌ Error checking loader status: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(check_loader_status())
