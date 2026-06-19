#!/usr/bin/env python3
"""Verify loader recovery status after Phase 1 failsafe retry attempts."""

from datetime import datetime, timezone

from utils.db.context import DatabaseContext


print("=" * 100)
print("PHASE 1 FAILSAFE RETRY VERIFICATION")
print("=" * 100)

try:
    with DatabaseContext("read") as cur:
        # Show what's happening NOW with incomplete loaders
        print("\n[1] INCOMPLETE LOADERS DETECTED BY PHASE 1 FAILSAFE:\n")

        cur.execute(
            """
            SELECT
                table_name,
                status,
                completion_pct,
                symbols_loaded,
                symbol_count,
                last_updated
            FROM data_loader_status
            WHERE (completion_pct < 95.0 OR status = 'INCOMPLETE')
                AND last_updated >= CURRENT_TIMESTAMP - INTERVAL '2 hours'
            ORDER BY last_updated DESC
        """
        )

        incomplete = cur.fetchall()

        if incomplete:
            for table_name, _status, completion_pct, symbols_loaded, symbol_count, last_updated in incomplete:
                completion_pct = completion_pct or 0
                missing = (symbol_count or 0) - (symbols_loaded or 0)
                if last_updated:
                    # Handle both aware and naive datetimes
                    if last_updated.tzinfo is None:
                        last_updated = last_updated.replace(tzinfo=timezone.utc)
                    age_min = (
                        datetime.now(timezone.utc) - last_updated
                    ).total_seconds() / 60
                else:
                    age_min = 0

                print(
                    f"  • {table_name:30s} {completion_pct:5.1f}%  "
                    f"({symbols_loaded}/{symbol_count} symbols, {missing} missing)  "
                    f"[Updated {age_min:.0f}m ago]"
                )

        # Show if any have RECOVERED (>=95%) after being incomplete
        print("\n[2] LOADERS THAT RECOVERED DURING RETRY:\n")

        cur.execute(
            """
            SELECT table_name, completion_pct, last_updated
            FROM data_loader_status
            WHERE completion_pct >= 95.0
                AND table_name IN ('value_metrics', 'positioning_metrics', 'growth_metrics')
                AND last_updated >= CURRENT_TIMESTAMP - INTERVAL '1 hour'
            ORDER BY last_updated DESC
        """
        )

        recovered = cur.fetchall()

        if recovered:
            for table_name, completion_pct, last_updated in recovered:
                if last_updated:
                    if last_updated.tzinfo is None:
                        last_updated = last_updated.replace(tzinfo=timezone.utc)
                    age_min = (
                        datetime.now(timezone.utc) - last_updated
                    ).total_seconds() / 60
                else:
                    age_min = 0
                print(f"  ✓ {table_name:30s} RECOVERED to {completion_pct:5.1f}% "
                      f"[{age_min:.0f}m ago]")
        else:
            print("  (None yet - retries may still be in progress)")

        # Show overall status
        print("\n[3] SUMMARY:\n")

        cur.execute(
            """
            SELECT
                COUNT(*) as total_loaders,
                SUM(CASE WHEN completion_pct >= 95.0 OR status = 'COMPLETED' THEN 1 ELSE 0 END) as passing,
                SUM(CASE WHEN completion_pct < 95.0 OR status = 'INCOMPLETE' THEN 1 ELSE 0 END) as failing
            FROM data_loader_status
            WHERE last_updated >= CURRENT_TIMESTAMP - INTERVAL '24 hours'
        """
        )

        total, passing, failing = cur.fetchone()
        passing = passing or 0
        failing = failing or 0

        print(f"  Recent loaders (24h): {total}")
        print(f"    • Passing (>=95%): {passing}")
        print(f"    • Failing (<95%):  {failing}")

        if failing > 0:
            print(f"\n  STATUS: {failing} loaders still below 95% threshold")
            print("  ACTION: Phase 1 failsafe is actively retrying these loaders")
        else:
            print("\n  STATUS: All loaders at >=95% completeness ✓")
            print("  ACTION: Pipeline ready - all data loaded, SLAs met")

except Exception as e:
    print(f"Error: {e}")
    import traceback

    traceback.print_exc()

print("\n" + "=" * 100)
