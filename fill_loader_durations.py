#!/usr/bin/env python3
"""Fill in missing execution_duration_sec and symbols_per_second for all loaders."""

import os
import psycopg2
from psycopg2.extras import RealDictCursor

conn = psycopg2.connect(
    host=os.getenv('DB_HOST', 'localhost'),
    user=os.getenv('DB_USER', 'postgres'),
    password=os.getenv('DB_PASSWORD', ''),
    database=os.getenv('DB_NAME', 'algo')
)

try:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        # First, find all loaders with NULL execution_duration_sec but valid start/end times
        cur.execute('''
            SELECT table_name,
                   execution_started,
                   execution_completed,
                   row_count,
                   execution_duration_sec,
                   symbols_per_second,
                   status
            FROM data_loader_status
            WHERE execution_started IS NOT NULL
              AND execution_completed IS NOT NULL
              AND (execution_duration_sec IS NULL OR execution_duration_sec = 0)
            ORDER BY table_name
        ''')

        missing_duration_rows = cur.fetchall()
        print(f"Found {len(missing_duration_rows)} loaders with missing/zero duration:\n")

        updates = []
        for row in missing_duration_rows:
            tbl = row['table_name']
            started = row['execution_started']
            completed = row['execution_completed']
            row_count = row['row_count']

            # Calculate duration in seconds
            if started and completed:
                duration_sec = (completed - started).total_seconds()

                # Calculate throughput (rows/second or symbols/second)
                throughput = row_count / duration_sec if duration_sec > 0 else 0

                print(f"  {tbl}: {duration_sec:.1f}s ({throughput:.1f}/s), {row_count} rows")
                updates.append((duration_sec, throughput, tbl))

        if updates:
            print(f"\nUpdating {len(updates)} loaders with calculated durations...")

            for duration_sec, throughput, tbl in updates:
                cur.execute('''
                    UPDATE data_loader_status
                    SET execution_duration_sec = %s,
                        symbols_per_second = %s
                    WHERE table_name = %s
                ''', (duration_sec, throughput, tbl))

            conn.commit()
            print(f"[OK] Updated {len(updates)} loaders")

        # Now show summary
        print("\n" + "="*70)
        cur.execute('''
            SELECT COUNT(*) as total,
                   COUNT(execution_duration_sec) as with_duration,
                   COUNT(CASE WHEN execution_duration_sec IS NULL THEN 1 END) as null_duration
            FROM data_loader_status
        ''')
        summary = cur.fetchone()
        total = summary['total']
        with_dur = summary['with_duration']
        null_dur = summary['null_duration']

        print(f"\nFinal Summary:")
        print(f"  Total loaders: {total}")
        print(f"  With duration: {with_dur} ({100*with_dur/total:.1f}%)")
        print(f"  Missing duration: {null_dur} ({100*null_dur/total:.1f}%)")

        if null_dur > 0:
            print(f"\nRemaining loaders without duration:")
            cur.execute('''
                SELECT table_name, status, execution_started, execution_completed
                FROM data_loader_status
                WHERE execution_duration_sec IS NULL
                ORDER BY table_name
            ''')
            for row in cur.fetchall():
                tbl = row['table_name']
                status = row['status']
                started = row['execution_started']
                completed = row['execution_completed']
                reason = ""
                if not started:
                    reason = "(no execution_started)"
                elif not completed:
                    reason = "(no execution_completed)"
                else:
                    reason = f"(status={status})"
                print(f"  {tbl}: {reason}")

finally:
    conn.close()
