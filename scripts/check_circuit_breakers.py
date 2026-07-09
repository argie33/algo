#!/usr/bin/env python3
import logging
from utils.db import DatabaseContext
import json
from datetime import datetime, timedelta

logging.basicConfig(level=logging.WARNING)

print("=" * 80)
print("CIRCUIT BREAKER ANALYSIS - FALSE POSITIVE DETECTION")
print("=" * 80)

try:
    with DatabaseContext("write") as cur:
        # Get detailed timeline of recent halts vs successful runs
        print("\n1. DETAILED TIMELINE: HALTS vs SUCCESSFUL RUNS")
        print("-" * 80)

        # Get all recent orchestrator runs
        cur.execute("""
            SELECT run_id, run_date, overall_status, halt_reason, created_at
            FROM orchestrator_execution_log
            ORDER BY created_at DESC
            LIMIT 15
        """)
        runs = cur.fetchall()
        print("Recent Orchestrator Runs (Last 15):")
        for run in runs:
            run_id, run_date, overall_status, halt_reason, created_at = run
            status_flag = "[HALTED]" if overall_status == "halt" else "[OK    ]"
            print(f"  {status_flag} {run_id} | {created_at.strftime('%Y-%m-%d %H:%M:%S')} | {overall_status}")
            if halt_reason:
                print(f"           Reason: {halt_reason}")

        # Analyze the halt flag update timestamp vs actual halts
        print("\n2. HALT FLAG vs ACTUAL BEHAVIOR")
        print("-" * 80)
        cur.execute("""
            SELECT key, value, updated_at
            FROM algo_config
            WHERE key = 'orchestrator_halt_enabled'
        """)
        row = cur.fetchone()
        if row:
            key, value, updated_at = row
            halt_flag = value.lower() == 'true'
            print(f"Config Flag: orchestrator_halt_enabled = {value}")
            print(f"Last Updated: {updated_at}")
            print(f"Interpretation: {'HALT IS ENABLED (trading blocked)' if halt_flag else 'HALT IS DISABLED (trading allowed)'}")

            # Check the most recent successful run time
            cur.execute("""
                SELECT created_at
                FROM orchestrator_execution_log
                WHERE overall_status = 'success'
                ORDER BY created_at DESC
                LIMIT 1
            """)
            success_row = cur.fetchone()
            if success_row:
                last_success = success_row[0]
                print(f"\nMost Recent Success Run: {last_success}")

                if last_success > updated_at:
                    print(f"  Note: Last success ({last_success}) is after flag update ({updated_at})")

        # Check for false positive by looking at weekly loss calculation
        print("\n3. WEEKLY LOSS CALCULATION")
        print("-" * 80)
        cur.execute("""
            SELECT
                (SELECT total_portfolio_value FROM algo_portfolio_snapshots ORDER BY snapshot_date DESC LIMIT 1) as current_value,
                (SELECT total_portfolio_value FROM algo_portfolio_snapshots WHERE snapshot_date <= CURRENT_DATE - get_interval_sql('7d') ORDER BY snapshot_date DESC LIMIT 1) as week_ago_value
        """)
        row = cur.fetchone()
        if row:
            current, week_ago = row
            if current and week_ago and week_ago > 0:
                weekly_loss = (current - week_ago) / week_ago * 100
                print(f"Current Portfolio Value: ${current:,.2f}")
                print(f"Portfolio Value 7 Days Ago: ${week_ago:,.2f}")
                print(f"Calculated Weekly Return: {weekly_loss:.2f}%")

                cur.execute("""SELECT value FROM algo_config WHERE key = 'max_weekly_loss_pct'""")
                threshold_row = cur.fetchone()
                if threshold_row:
                    threshold = float(threshold_row[0])
                    threshold_negative = -threshold
                    print(f"Max Weekly Loss Threshold: {threshold_negative:.1f}%")
                    if weekly_loss <= threshold_negative:
                        print(f"Weekly loss {weekly_loss:.2f}% <= {threshold_negative:.1f}% - HALT IS JUSTIFIED")
                    else:
                        print(f"Weekly loss {weekly_loss:.2f}% > {threshold_negative:.1f}% threshold - SHOULD NOT halt")

        # Summary of all circuit breaker checks from latest run
        print("\n4. ALL CIRCUIT BREAKER CHECKS (Latest Success Run)")
        print("-" * 80)
        cur.execute("""
            SELECT phase_results
            FROM orchestrator_execution_log
            WHERE overall_status = 'success'
            ORDER BY created_at DESC
            LIMIT 1
        """)
        row = cur.fetchone()
        if row and row[0]:
            try:
                phases = json.loads(row[0]) if isinstance(row[0], str) else row[0]
                phase_2 = phases.get('2', {})
                if 'data' in phase_2 and isinstance(phase_2['data'], dict):
                    checks = phase_2['data'].get('checks', {})
                    if checks:
                        print(f"Found {len(checks)} circuit breaker checks:")
                        halted_count = 0
                        for check_name, check_data in sorted(checks.items()):
                            if isinstance(check_data, dict):
                                halted = check_data.get('halted', False)
                                if halted:
                                    halted_count += 1
                                flag = "HALT" if halted else "OK  "
                                label = check_data.get('label', check_name)
                                reason = check_data.get('reason', 'N/A')
                                print(f"  [{flag}] {label:40s} | {reason[:60]}")
                        print(f"\nTotal checks: {len(checks)}, Halted: {halted_count}, Passing: {len(checks) - halted_count}")
            except Exception as e:
                print(f"Could not parse latest success run: {e}")

        # Count halts by reason
        print("\n5. HALT REASONS (Last 7 Days)")
        print("-" * 80)
        cur.execute("""
            SELECT
                details,
                COUNT(*) as count,
                MAX(created_at) as latest
            FROM algo_audit_log
            WHERE action_type = 'circuit_breaker_halt'
              AND created_at >= CURRENT_TIMESTAMP - get_interval_sql('7d')
            GROUP BY details
            ORDER BY count DESC
        """)
        rows = cur.fetchall()
        if rows:
            for row in rows:
                details_str, count, latest = row
                if details_str:
                    try:
                        data = json.loads(details_str) if isinstance(details_str, str) else details_str
                        if isinstance(data, dict) and data.get('halt_reasons'):
                            reason = data['halt_reasons'][0] if data['halt_reasons'] else 'Unknown'
                            print(f"  ({count:3d}x) {reason}")
                            print(f"        Latest: {latest}")
                    except json.JSONDecodeError as e:
                        logging.debug(f"Could not parse halt reason details JSON: {e}")
                    except (TypeError, KeyError, IndexError) as e:
                        logging.debug(f"Halt reason data structure invalid: {e}")
                    except Exception as e:
                        logging.warning(f"Unexpected error parsing halt reason: {type(e).__name__}: {e}")

        print("\n6. RECENT FALSE POSITIVE ANALYSIS")
        print("-" * 80)

        # Get most recent halt event with details
        cur.execute("""
            SELECT created_at, details
            FROM algo_audit_log
            WHERE action_type = 'circuit_breaker_halt'
            ORDER BY created_at DESC
            LIMIT 1
        """)
        row = cur.fetchone()
        if row:
            latest_halt_time, details = row
            print(f"Most Recent Halt: {latest_halt_time}")
            if details:
                try:
                    data = json.loads(details) if isinstance(details, str) else details
                    if isinstance(data, dict):
                        if data.get('halt_reasons'):
                            print("Reasons:")
                            for reason in data['halt_reasons']:
                                print(f"  - {reason}")
                        if data.get('checks'):
                            halted_checks = {k: v for k, v in data['checks'].items() if v.get('halted')}
                            if halted_checks:
                                print("\nHalted Checks Details:")
                                for check_name, check_data in halted_checks.items():
                                    print(f"  {check_name}:")
                                    print(f"    Reason: {check_data.get('reason')}")
                                    if 'value' in check_data:
                                        print(f"    Value: {check_data['value']}")
                                    if 'threshold' in check_data:
                                        print(f"    Threshold: {check_data['threshold']}")
                except Exception as e:
                    pass

        # Check if any recent halts appear to be false positives
        print("\n7. FALSE POSITIVE DETECTION SUMMARY")
        print("-" * 80)

        # Check market stage stale data halts
        cur.execute("""
            SELECT COUNT(*) as stale_data_halts
            FROM algo_audit_log
            WHERE action_type = 'circuit_breaker_halt'
              AND details::text ILIKE '%stale%'
              AND created_at >= CURRENT_TIMESTAMP - get_interval_sql('1d')
        """)
        stale_row = cur.fetchone()
        if stale_row:
            stale_count = stale_row[0]
            if stale_count > 0:
                print(f"POTENTIAL FALSE POSITIVES: {stale_count} halts due to 'stale data' in last 24h")
                print("These may be false positives if data loading issues resolved.")

except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 80)
