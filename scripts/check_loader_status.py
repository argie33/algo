#!/usr/bin/env python3
"""Check actual loader execution status in AWS database."""

from utils.db.context import DatabaseContext


print("Checking recent loader execution status in AWS...\n")

try:
    with DatabaseContext("read") as cur:
        # Get the 15 most recent loader runs
        cur.execute(
            """
            SELECT
                table_name,
                status,
                completion_pct,
                symbols_loaded,
                symbol_count,
                execution_started,
                execution_completed,
                last_updated
            FROM data_loader_status
            WHERE last_updated >= CURRENT_TIMESTAMP - INTERVAL '24 hours'
            ORDER BY last_updated DESC
            LIMIT 15
        """
        )

        rows = cur.fetchall()

        if not rows:
            print("No loader executions found in last 24 hours.")
        else:
            print("Recent Loader Execution Status (Last 24 Hours):\n")
            print(
                f"{'Loader':<40} {'Status':<12} {'Completeness':<15} {'Exec Time':<12}"
            )
            print("-" * 85)

            for row in rows:
                (
                    table_name,
                    status,
                    completion_pct,
                    symbols_loaded,
                    symbol_count,
                    exec_started,
                    exec_completed,
                    last_updated,
                ) = row

                completion_pct = completion_pct or 0

                # Calculate execution time
                exec_time_sec = None
                if exec_started and exec_completed:
                    exec_time_sec = (exec_completed - exec_started).total_seconds()

                exec_time_min = (exec_time_sec / 60) if exec_time_sec else 0

                # Format completion percentage with pass/fail indicator
                completion_indicator = "[PASS]" if completion_pct >= 95 else "[FAIL]"

                print(
                    f"{table_name:<40} {status:<12} {completion_pct:>5.1f}% {completion_indicator:<8} {exec_time_min:>5.0f}m"
                )

            # Summary stats
            print("\n" + "=" * 85)

            completed_count = sum(1 for r in rows if r[1] == "COMPLETED")
            incomplete_count = sum(1 for r in rows if r[1] == "INCOMPLETE")
            completeness_pass = sum(1 for r in rows if (r[2] or 0) >= 95)
            completeness_fail = sum(1 for r in rows if (r[2] or 0) < 95)

            print(f"\nSummary of {len(rows)} recent runs:")
            print(f"  Status: {completed_count} COMPLETED, {incomplete_count} INCOMPLETE")
            print(
                f"  Completeness: {completeness_pass} PASS (>=95%), {completeness_fail} FAIL (<95%)"
            )

            if completeness_fail > 0:
                print("\n*** ISSUE DETECTED: Some loaders not meeting 95% completeness threshold ***")
            else:
                print("\n*** SUCCESS: All recent loaders meeting 95% completeness threshold ***")

except Exception as e:
    print(f"Error connecting to database: {e}")
    import traceback

    traceback.print_exc()
