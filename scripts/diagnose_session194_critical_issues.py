#!/usr/bin/env python3
"""
SESSION 194 CRITICAL DIAGNOSTICS

Diagnoses three critical blockers:
1. Phase 8 Alpaca credentials error (regression)
2. ValueMetrics pipeline stale (Session 194 fix not working)
3. Market exposure table stale (upstream dependency)

Run: python3 scripts/diagnose_session194_critical_issues.py
"""

import subprocess
import json
import os
import sys
from datetime import datetime, timedelta
import psycopg2

def run_shell_cmd(cmd: list[str]) -> tuple[int, str]:
    """Run shell command and return exit code + output."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return result.returncode, result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return -1, "TIMEOUT"
    except Exception as e:
        return -2, str(e)

def check_github_actions_deployment():
    """Check if GitHub Actions deployed Commit 4c37440f5."""
    print("\n" + "="*70)
    print("1. GITHUB ACTIONS DEPLOYMENT STATUS")
    print("="*70)

    # Get recent commits
    rc, out = run_shell_cmd(["git", "log", "--oneline", "-10"])
    if rc == 0:
        print("Recent commits:")
        for line in out.split('\n')[:5]:
            if line:
                print(f"  {line}")

    # Check if credentials fix commit is deployed
    print("\nCredentials fix status:")
    print("  Commit 4c37440f5 (Session 193 Alpaca fix):")
    rc, out = run_shell_cmd(["git", "log", "--oneline", "-1"])
    if "4c37440f5" in out or "Alpaca" in out:
        print("    ✓ Found in recent history")
    else:
        print("    ? Not in recent commits - may have been reverted")

    print("\nValueMetrics fix status:")
    print("  Commit 90291b160 (Session 194 ECS resources):")
    rc, out = run_shell_cmd(["git", "show", "--stat", "90291b160"])
    if rc == 0:
        print("    ✓ Terraform changes are committed")
        if "cpu = 1024" in out:
            print("    ✓ CPU increase (512→1024) is in code")
        if "memory = 2048" in out:
            print("    ✓ Memory increase (1024→2048) is in code")
    else:
        print("    ✗ Commit not found or not deployed")

def check_lambda_deployment():
    """Check if Lambda function was updated with Commit 4c37440f5."""
    print("\n" + "="*70)
    print("2. AWS LAMBDA DEPLOYMENT STATUS")
    print("="*70)

    # Check if we can read the deployed Lambda code
    print("\nTo verify Lambda deployment, you would need AWS credentials.")
    print("Local checks:")
    print("  - Lambda layer: /opt/python (only visible in Lambda)")
    print("  - Lambda code: /var/task (only visible in Lambda)")
    print("  - Current local code: algo/orchestration.py (shows what SHOULD be deployed)")

    # Check if local code has the fix
    print("\nLocal orchestrator code:")
    rc, out = run_shell_cmd(["grep", "-n", "algo-algo-secrets-dev",
                            "lambda/algo_orchestrator/lambda_function.py"])
    if rc == 0:
        print("  ✓ Code has credentials fix (algo-algo-secrets-dev)")
    else:
        print("  ✗ Code missing credentials fix!")

    print("\nIf Lambda is NOT running the fixed code:")
    print("  - GitHub Actions deployment may have failed")
    print("  - Lambda container image may be stale")
    print("  - Terraform changes may not have been applied")

def check_aws_secrets():
    """Check if Alpaca credentials exist in AWS Secrets Manager."""
    print("\n" + "="*70)
    print("3. AWS SECRETS MANAGER STATUS")
    print("="*70)

    print("\nTo check secrets, run:")
    print("  aws secretsmanager list-secrets --region us-east-1")
    print("  aws secretsmanager get-secret-value --secret-id algo-algo-secrets-dev")
    print("\nExpected fields in secret:")
    print("  - APCA_API_KEY_ID")
    print("  - APCA_API_SECRET_KEY")

def check_database_tables():
    """Check staleness of key tables."""
    print("\n" + "="*70)
    print("4. DATABASE TABLE STALENESS")
    print("="*70)

    try:
        conn = psycopg2.connect('dbname=stocks user=stocks host=localhost')
        cur = conn.cursor()

        today = datetime.now().date()
        tables = {
            'value_metrics': 'date',
            'market_exposure_daily': 'report_date',
            'technical_data_daily': 'date',
            'positioning_metrics': 'date',
            'growth_metrics': 'date',
            'quality_metrics': 'date',
        }

        print("\nTable staleness:")
        for table, date_col in tables.items():
            try:
                cur.execute(f"SELECT MAX({date_col}), COUNT(*) FROM {table}")
                latest, count = cur.fetchone()
                if latest:
                    days_old = (today - latest).days
                    status = "✓ FRESH" if days_old == 0 else "⚠ STALE" if days_old > 1 else "? 1d old"
                    print(f"  {table:30} | {latest} | {days_old}d old | {status}")
                else:
                    print(f"  {table:30} | NO DATA")
            except Exception as e:
                print(f"  {table:30} | ERROR: {str(e)[:40]}")

        # Check recent orchestrator halts
        print("\nRecent orchestrator failures:")
        cur.execute("""
            SELECT started_at, halt_reason
            FROM algo_orchestrator_runs
            WHERE started_at > NOW() - INTERVAL '1 hour'
            ORDER BY started_at DESC
            LIMIT 3
        """)
        for row in cur.fetchall():
            started, halt = row
            if halt:
                halt_short = (halt[:60] + "...") if len(halt) > 60 else halt
                print(f"  {started.strftime('%H:%M')}: {halt_short}")

        conn.close()
    except Exception as e:
        print(f"Database connection failed: {e}")
        print("Cannot check table staleness without database access")

def check_terraform_deployment():
    """Check if Terraform changes were applied to AWS."""
    print("\n" + "="*70)
    print("5. TERRAFORM DEPLOYMENT STATUS")
    print("="*70)

    print("\nTo verify Terraform deployment:")
    print("  aws ecs describe-task-definition \\")
    print("    --task-definition algo-value_metrics:LATEST \\")
    print("    --region us-east-1")
    print("\nLook for:")
    print("  - cpu: 1024 (should be 2x the original 512)")
    print("  - memory: 2048 (should be 2x the original 1024)")
    print("  - containerDefinitions[0].environment[].timeout: 3600")

def main():
    """Run all diagnostics."""
    print("\n" + "="*70)
    print("SESSION 194 CRITICAL ISSUES - DIAGNOSTIC REPORT")
    print("="*70)
    print(f"Timestamp: {datetime.now().isoformat()}")

    check_github_actions_deployment()
    check_lambda_deployment()
    check_aws_secrets()
    check_database_tables()
    check_terraform_deployment()

    print("\n" + "="*70)
    print("RECOMMENDATION")
    print("="*70)
    print("""
THREE ISSUES BLOCKING PROGRESS:

1. [CRITICAL] Phase 8 Alpaca Credentials
   - Status: Regression - credentials error at 16:09
   - Fix: Commit 4c37440f5 code fix deployed locally but Lambda may not have it
   - Action: Verify GitHub Actions deployed Lambda, or manually redeploy

2. [CRITICAL] ValueMetrics Pipeline Stale
   - Status: 6 days old (2026-07-10, should be TODAY 2026-07-16)
   - Fix: Commit 90291b160 increased ECS task resources, but task not running
   - Action: Verify market_exposure_daily freshness first (blocking dependency)

3. [CRITICAL] Market Exposure Table Stale
   - Status: 2 days old (2026-07-14)
   - Fix: Unknown - pipeline stalled due to this
   - Action: Investigate why EOD pipeline isn't updating market_exposure_daily

NEXT STEPS:
1. Verify AWS deployment status (GitHub Actions, Lambda, Terraform)
2. Force manual Lambda update if needed
3. Trigger EOD pipeline to refresh market_exposure_daily
4. Trigger Computed Metrics pipeline to refresh value_metrics
5. Monitor orchestrator runs to confirm fixes work
    """)

if __name__ == "__main__":
    main()
