#!/usr/bin/env python3
"""Monitor for 1 PM orchestrator run and report when it completes."""

import time
from datetime import datetime
from datetime import time as dt_time
from zoneinfo import ZoneInfo

import psycopg2

ET = ZoneInfo("America/New_York")


def check_for_run():
    """Check if a run occurred in the past 2 hours (covers 1 PM run)."""
    conn = psycopg2.connect("dbname=stocks user=stocks host=localhost")
    cur = conn.cursor()

    cur.execute("""
    SELECT started_at, completed_at, overall_status, halt_reason
    FROM algo_orchestrator_runs
    WHERE started_at > NOW() - INTERVAL '2 hours'
    ORDER BY started_at DESC
    LIMIT 1
    """)
    result = cur.fetchone()
    conn.close()

    return result


def main():
    """Monitor loop until 1 PM run is found."""
    print(f"[{datetime.now(ET).strftime('%H:%M:%S ET')}] Starting 1 PM run monitor...")
    print("Checking database every 30 seconds for orchestrator execution...")
    print()

    last_seen_start = None

    while True:
        now = datetime.now(ET)
        now_time = now.time()

        # Stop monitoring after 3:30 PM (plenty of time after 3 PM run)
        if now_time > dt_time(15, 30):
            print(f"\n[{now.strftime('%H:%M:%S ET')}] After 3:30 PM - all sessions should be done. Stopping monitor.")
            break

        result = check_for_run()

        if result:
            started_at, completed_at, status, halt = result

            # Only report new runs
            if last_seen_start is None or started_at > last_seen_start:
                last_seen_start = started_at

                # Check if this is the 1 PM run (started between 12:58 PM and 1:02 PM)
                start_time = started_at.time()
                is_1pm_run = dt_time(12, 58) <= start_time <= dt_time(13, 2)

                print(f"\n{'='*70}")
                print(f"[{now.strftime('%H:%M:%S ET')}] RUN DETECTED:")
                print(f"  Started:   {started_at.strftime('%H:%M:%S ET')}")
                if completed_at:
                    print(f"  Completed: {completed_at.strftime('%H:%M:%S ET')}")
                    duration = (completed_at - started_at).total_seconds()
                    print(f"  Duration:  {int(duration)} seconds")
                else:
                    print("  Completed: (still running)")
                print(f"  Status:    {status}")
                if halt:
                    print(f"  Halt:      {halt}")

                if is_1pm_run:
                    print(f"\n  SUCCESS: 1 PM run {'completed' if completed_at else 'started'}!")
                    if completed_at and status == "success":
                        print("  ✓ System is ready - 1 PM automation working correctly")
                        return 0

        time.sleep(30)  # Check every 30 seconds


if __name__ == "__main__":
    main()
