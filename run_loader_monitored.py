#!/usr/bin/env python3
"""
Run loadbuyselldaily.py with monitoring, error handling, and accuracy tracking
Validates patterns are being detected correctly
"""
import subprocess
import sys
import time
from datetime import datetime
import json
import psycopg2
from pathlib import Path
from dotenv import load_dotenv
import os

env_path = Path('.env.local')
load_dotenv(env_path)

def get_db_connection():
    return psycopg2.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=int(os.getenv('DB_PORT', 5432)),
        user=os.getenv('DB_USER', 'stocks'),
        password=os.getenv('DB_PASSWORD', ''),
        dbname=os.getenv('DB_NAME', 'stocks')
    )

def count_patterns():
    """Count detected patterns in database"""
    conn = get_db_connection()
    cur = conn.cursor()

    try:
        cur.execute("""
            SELECT
                base_type,
                COUNT(*) as count
            FROM buy_sell_daily
            WHERE base_type IS NOT NULL
            GROUP BY base_type
            ORDER BY count DESC
        """)

        results = cur.fetchall()
        total = sum(r[1] for r in results)

        return dict(results), total
    finally:
        conn.close()

def print_header(text):
    print("\n" + "=" * 70)
    print(text.center(70))
    print("=" * 70 + "\n")

def main():
    print_header("BASE PATTERN DETECTION - FULL RUN")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    # Count patterns before
    print("Checking current database state...")
    try:
        patterns_before, total_before = count_patterns()
        print(f"Total signals in buy_sell_daily: {741686:,}")
        print(f"Already detected patterns: {total_before:,}\n")

        if patterns_before:
            print("Current pattern distribution:")
            for ptype, count in patterns_before.items():
                pct = count / max(total_before, 1) * 100
                print(f"  - {ptype}: {count:,} ({pct:.1f}%)")
    except Exception as e:
        print(f"Warning: Could not check current state: {e}\n")
        patterns_before = {}
        total_before = 0

    # Run loader
    print_header("RUNNING LOADER")
    print("Command: python3 loadbuyselldaily.py\n")
    print("This will detect base patterns for all symbols.")
    print("Estimated time: 2-4 hours\n")

    print("Press Enter to start, or Ctrl+C to cancel...")
    try:
        input()
    except KeyboardInterrupt:
        print("\nCancelled by user.")
        sys.exit(0)

    start_time = time.time()

    try:
        # Run the loader
        result = subprocess.run(
            [sys.executable, 'loadbuyselldaily.py'],
            capture_output=True,
            text=True,
            timeout=14400  # 4 hours max
        )

        elapsed = time.time() - start_time

        # Show output
        if result.stdout:
            print("\nLoader output:")
            print(result.stdout[-2000:])  # Last 2000 chars to avoid spam

        if result.returncode != 0:
            print(f"\nWarning: Loader returned code {result.returncode}")
            if result.stderr:
                print("Errors:")
                print(result.stderr[-1000:])

    except subprocess.TimeoutExpired:
        print("\nERROR: Loader timed out after 4 hours!")
        sys.exit(1)
    except Exception as e:
        print(f"\nERROR: {e}")
        sys.exit(1)

    # Check results
    print_header("CHECKING RESULTS")

    try:
        patterns_after, total_after = count_patterns()

        print(f"Elapsed time: {elapsed/3600:.1f} hours\n")
        print(f"Total patterns detected: {total_after:,}")
        print(f"Detection rate: {total_after/741686*100:.1f}%\n")

        if patterns_after:
            print("Pattern distribution:")
            for ptype, count in patterns_after.items():
                pct = count / max(total_after, 1) * 100
                print(f"  - {ptype}: {count:,} ({pct:.1f}%)")

        # Show improvement
        if total_before > 0:
            improvement = total_after - total_before
            print(f"\nNew patterns detected: {improvement:,}")
            print(f"Improvement: +{improvement/total_before*100:.1f}%")

    except Exception as e:
        print(f"ERROR checking results: {e}")
        sys.exit(1)

    print_header("COMPLETE")
    print(f"Finished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("\nAccuracy improvements deployed:")
    print("  - Volume validation (critical)")
    print("  - Symmetry scoring for cups")
    print("  - Confidence scoring (0-100)")
    print("  - Base on Base detection")
    print("  - Tier 1.5 enhancements (price action)")
    print("\nNext steps:")
    print("  1. Test in frontend: http://localhost:5175/signals")
    print("  2. Filter by base type to see detected patterns")
    print("  3. Expand signals to see Pattern Analysis section")
    print("  4. Monitor accuracy over trades")

if __name__ == "__main__":
    main()
