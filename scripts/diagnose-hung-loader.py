#!/usr/bin/env python3
"""Diagnose why swing_trader_scores loader wasn't killed by orchestrator.

Focus: Check current ECS task status for swing_trader_scores hung task.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.database_context import DatabaseContext
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
import logging

logging.basicConfig(level='INFO', format='%(message)s')

def diagnose():
    print("\n" + "="*80)
    print("DIAGNOSTIC: Hung Loader (swing_trader_scores) Analysis")
    print("="*80)

    try:
        # Check data_loader_status
        print("\n[1] Database loader status for swing_trader_scores:")
        with DatabaseContext('read') as cur:
            cur.execute("""
                SELECT table_name, status, last_updated, completed_symbols, failed_symbols
                FROM data_loader_status
                WHERE table_name = 'swing_trader_scores'
            """)
            loader_status = cur.fetchone()

            if loader_status:
                table_name, status, last_updated, completed, failed = loader_status
                print(f"    Status: {status}")
                print(f"    Last Updated: {last_updated}")
                if completed is not None:
                    print(f"    Completed Symbols: {completed}")
                if failed is not None:
                    print(f"    Failed Symbols: {failed}")

                if last_updated and isinstance(last_updated, str):
                    try:
                        last_updated = datetime.fromisoformat(last_updated.replace('Z', '+00:00'))
                    except:
                        pass

                if last_updated and hasattr(last_updated, 'replace'):
                    age_seconds = (datetime.now(timezone.utc) - last_updated).total_seconds()
                    age_hours = age_seconds / 3600
                    print(f"    Age: {age_hours:.1f} hours ({int(age_seconds/60)} minutes)")
                    if age_hours > 2:
                        print(f"    >> LOADER HUNG: Running for {age_hours:.1f}h (expected max ~30 min)")
            else:
                print("    [INFO] No loader status found (loader may not have started yet)")

        # Check ECS tasks
        print("\n[2] ECS task status for swing_trader_scores:")
        try:
            import boto3
            import os

            ecs = boto3.client('ecs', region_name=os.getenv('AWS_REGION', 'us-east-1'))
            cluster = os.getenv('ECS_CLUSTER_ARN', 'algo-cluster')

            response = ecs.list_tasks(cluster=cluster, desiredStatus='RUNNING')
            if not response.get('taskArns'):
                print("    [INFO] No running ECS tasks found")
                return

            task_details = ecs.describe_tasks(cluster=cluster, tasks=response['taskArns'])
            found_swing = False

            for task in task_details.get('tasks', []):
                task_def = task.get('taskDefinitionArn', '')
                if 'swing_trader_scores' in task_def:
                    found_swing = True
                    started_at = task.get('startedAt')

                    # Calculate task age
                    if started_at:
                        if started_at.tzinfo is None:
                            started_at = started_at.replace(tzinfo=timezone.utc)
                        age_seconds = (datetime.now(timezone.utc) - started_at).total_seconds()
                        age_hours = age_seconds / 3600
                    else:
                        age_hours = 0

                    print(f"    [ERROR] FOUND HUNG TASK")
                    print(f"    Task ARN: {task.get('taskArn')}")
                    print(f"    Task Status: {task.get('lastStatus')}")
                    print(f"    Started: {started_at}")
                    print(f"    Age: {age_hours:.1f} hours")

                    # Determine if it should have been killed
                    now_et = datetime.now(timezone.utc).astimezone(ZoneInfo("America/New_York"))
                    orch_times = [(9, 30), (13, 0), (15, 0), (17, 30)]

                    # Find next orchestrator run
                    next_orch = None
                    for h, m in orch_times:
                        t = now_et.replace(hour=h, minute=m, second=0, microsecond=0)
                        if t > now_et:
                            next_orch = t
                            break

                    if next_orch:
                        max_runtime_hours = ((next_orch - timedelta(minutes=15)) - now_et).total_seconds() / 3600
                        print(f"    Next Orch Run: {next_orch.strftime('%H:%M %Z')}")
                        print(f"    Max Runtime Before Kill: {max_runtime_hours:.1f}h")
                        print(f"    >> KILL DECISION: {age_hours:.1f}h > {max_runtime_hours:.1f}h = {age_hours > max_runtime_hours}")

                        if age_hours > max_runtime_hours:
                            print(f"    >> BUG: Orchestrator should have killed this task!")
                            print(f"    >> Check: Did orchestrator run since {started_at}?")
                            print(f"    >> Check: CloudWatch logs for [OOM_PREVENTION] messages")

            if not found_swing:
                print("    [OK] No hung swing_trader_scores task (was killed or completed)")

        except Exception as e:
            print(f"    [WARN] Could not check ECS (need AWS credentials): {e}")
            print(f"    Error type: {type(e).__name__}")

    except Exception as e:
        print(f"\n[ERROR] Diagnosis failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    diagnose()
