#!/usr/bin/env python3
"""Diagnose why swing_trader_scores loader wasn't killed by orchestrator.

Expected behavior:
- Loader started: 10:13 AM ET (2026-06-07)
- Orchestrator runs at: 9:30 AM, 1 PM, 3 PM, 5:30 PM ET
- At 1 PM run: loader age = 2h 47min, next_orch = 3 PM (95 min away), max_runtime = 80 min
  → AGE (167 min) > max_runtime (80 min) → SHOULD KILL

This script checks:
1. When did orchestrator last run?
2. Did it log _kill_long_running_loaders?
3. Was swing_trader_scores in the monitored set?
4. If kill was triggered, did task termination succeed?
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.database_context import DatabaseContext
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
import json

def diagnose():
    print("\n" + "="*80)
    print("DIAGNOSTIC: Hung Loader Kill Logic Analysis")
    print("="*80)
    
    try:
        with DatabaseContext('read') as cur:
            # Check orchestrator_execution_log for recent runs
            print("\n[1] Recent orchestrator runs:")
            cur.execute("""
                SELECT run_id, started_at, status, phases
                FROM orchestrator_execution_log
                WHERE run_date = CURRENT_DATE
                ORDER BY started_at DESC
                LIMIT 10
            """)
            orch_runs = cur.fetchall()
            
            if not orch_runs:
                print("   ✗ No orchestrator runs found for today. Check if orchestrator is running.")
                return
            
            for run_id, started_at, status, phases in orch_runs:
                print(f"   {started_at} | {run_id:30s} | {status:10s}")
                
                # Check if Phase 1 (pre-flight) ran successfully
                if phases:
                    try:
                        phases_data = json.loads(phases) if isinstance(phases, str) else phases
                        # phases is an array of phase results
                        if isinstance(phases_data, list):
                            for phase in phases_data:
                                if 'name' in phase and 'oom_prevention' in str(phase.get('name', '')).lower():
                                    print(f"      → OOM Prevention logged: {phase.get('status')} ({phase.get('summary')})")
                    except Exception as e:
                        pass
            
            # Check data_loader_status for swing_trader_scores
            print("\n[2] Loader status for swing_trader_scores:")
            cur.execute("""
                SELECT table_name, status, last_updated, completed_symbols, failed_symbols
                FROM data_loader_status
                WHERE table_name = 'swing_trader_scores'
            """)
            loader_status = cur.fetchone()
            
            if loader_status:
                table_name, status, last_updated, completed, failed = loader_status
                print(f"   Status: {status}")
                print(f"   Last Updated: {last_updated}")
                if completed is not None:
                    print(f"   Completed Symbols: {completed}")
                if failed is not None:
                    print(f"   Failed Symbols: {failed}")
                
                # Calculate age
                if last_updated:
                    if isinstance(last_updated, str):
                        last_updated = datetime.fromisoformat(last_updated.replace('Z', '+00:00'))
                    age = datetime.now(timezone.utc) - last_updated
                    print(f"   Age: {age.total_seconds()/3600:.1f}h")
            else:
                print("   ✗ No loader status found for swing_trader_scores")
            
            # Check ECS task status
            print("\n[3] ECS task status (requires AWS credentials):")
            try:
                import boto3
                ecs = boto3.client('ecs', region_name='us-east-1')
                
                # List running tasks
                response = ecs.list_tasks(cluster='algo-cluster', desiredStatus='RUNNING')
                if response.get('taskArns'):
                    task_details = ecs.describe_tasks(cluster='algo-cluster', tasks=response['taskArns'])
                    for task in task_details.get('tasks', []):
                        task_def = task.get('taskDefinitionArn', '')
                        if 'swing_trader_scores' in task_def:
                            started_at = task.get('startedAt')
                            age = (datetime.now(timezone.utc) - started_at).total_seconds() / 3600 if started_at else 0
                            print(f"   Found running task: {task.get('taskArn')}")
                            print(f"   Started: {started_at}")
                            print(f"   Age: {age:.1f}h")
                            
                            # Calculate if it should have been killed
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
                                max_runtime = (next_orch - timedelta(minutes=15) - now_et).total_seconds() / 3600
                                print(f"   Next Orchestrator Run: {next_orch.strftime('%H:%M %Z')}")
                                print(f"   Max Runtime Before Kill: {max_runtime:.1f}h")
                                print(f"   Should Kill?: {age > max_runtime}")
                else:
                    print("   ✓ No running swing_trader_scores task found (was successfully killed or completed)")
            except Exception as e:
                print(f"   ⚠ Could not check ECS (need AWS credentials): {e}")
            
            # Check CloudWatch logs for orchestrator execution
            print("\n[4] Recent orchestrator log messages:")
            print("   (Check CloudWatch for: '[OOM_PREVENTION] Killing swing_trader_scores task')")
            print("   (Or: '[CHECK] Killing long-running analytics loaders...')")
            
    except Exception as e:
        print(f"\n✗ Error during diagnosis: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    diagnose()
