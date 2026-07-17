#!/usr/bin/env python3
"""
Verify AWS deployment status and Lambda function updates.
Checks if Alpaca credentials fix (Session 193) has been deployed to AWS Lambda.
"""

import json
import subprocess
import time
from datetime import datetime


def check_github_actions_status():
    """Check if GitHub Actions CI passed and Terraform is deploying."""
    result = subprocess.run(
        ["gh", "run", "list", "--repo", "argie33/algo", "--branch", "main", "--limit", "10",
         "--json", "name,status,conclusion"],
        capture_output=True,
        text=True,
        timeout=10
    )

    if result.returncode != 0:
        return {"error": "Failed to fetch GitHub Actions status"}

    runs = json.loads(result.stdout)

    status_info = {
        "ci": None,
        "terraform": None,
        "deployment_ready": False
    }

    for run in runs:
        if run["name"] == "CI":
            status_info["ci"] = f"{run['status']} / {run.get('conclusion', 'pending')}"
            if run.get("conclusion") == "success":
                status_info["deployment_ready"] = True

        if "Terraform" in run["name"]:
            status_info["terraform"] = f"{run['status']} / {run.get('conclusion', 'pending')}"

    return status_info


def check_lambda_code():
    """Check if Lambda code has the credentials fix by looking at local code."""
    try:
        with open("lambda/algo_orchestrator/lambda_function.py", "r") as f:
            content = f.read()

        has_credentials_fix = "_load_alpaca_credentials_from_secrets" in content
        has_secret_fallback = "algo-algo-secrets-dev" in content and "algo/alpaca" in content

        return {
            "has_credentials_fix": has_credentials_fix,
            "has_secret_fallback": has_secret_fallback,
            "deployed_in_code": has_credentials_fix and has_secret_fallback
        }
    except Exception as e:
        return {"error": str(e)}


def check_database_status():
    """Check actual data freshness in database."""
    try:
        import psycopg2
        import os

        conn = psycopg2.connect(
            dbname='stocks',
            user='stocks',
            host='localhost',
            password=os.environ.get('STOCKS_DB_PASSWORD', ''),
            port=5432
        )
        cur = conn.cursor()

        # Check market exposure freshness
        cur.execute("""
            SELECT MAX(date), CURRENT_DATE - MAX(date) as days_old
            FROM market_exposure_daily
        """)
        market_exp = cur.fetchone()

        # Check value metrics freshness
        cur.execute("""
            SELECT MAX(date), CURRENT_DATE - MAX(date) as days_old
            FROM value_metrics
        """)
        value_metrics = cur.fetchone()

        # Check last orchestrator run
        cur.execute("""
            SELECT started_at, overall_status, halt_reason
            FROM algo_orchestrator_runs
            ORDER BY started_at DESC
            LIMIT 1
        """)
        last_run = cur.fetchone()

        cur.close()
        conn.close()

        return {
            "market_exposure": f"{market_exp[0]} ({market_exp[1]} days old)" if market_exp else "N/A",
            "value_metrics": f"{value_metrics[0]} ({value_metrics[1]} days old)" if value_metrics else "N/A",
            "last_run": f"{last_run[0]}: {last_run[1]} - {last_run[2][:80]}" if last_run else "No runs"
        }
    except Exception as e:
        return {"error": f"Database connection failed: {e}"}


def main():
    print("=" * 80)
    print("AWS DEPLOYMENT STATUS CHECK")
    print("=" * 80)
    print(f"Time: {datetime.now().isoformat()}\n")

    print("1. GITHUB ACTIONS STATUS")
    print("-" * 80)
    gh_status = check_github_actions_status()
    if "error" in gh_status:
        print(f"ERROR: {gh_status['error']}")
    else:
        print(f"CI Status: {gh_status['ci']}")
        print(f"Terraform Status: {gh_status['terraform']}")
        print(f"Deployment Ready: {gh_status['deployment_ready']}")

    print("\n2. LAMBDA CODE VERIFICATION")
    print("-" * 80)
    code_status = check_lambda_code()
    if "error" in code_status:
        print(f"ERROR: {code_status['error']}")
    else:
        print(f"Credentials fix in code: {code_status['deployed_in_code']}")
        if code_status['deployed_in_code']:
            print("  - _load_alpaca_credentials_from_secrets() function exists")
            print("  - Tries both 'algo-algo-secrets-dev' and 'algo/alpaca' secrets")

    print("\n3. DATABASE STATUS")
    print("-" * 80)
    db_status = check_database_status()
    if "error" in db_status:
        print(f"ERROR: {db_status['error']}")
    else:
        print(f"Market Exposure: {db_status['market_exposure']}")
        print(f"Value Metrics: {db_status['value_metrics']}")
        print(f"Last Orchestrator Run: {db_status['last_run']}")

    print("\n" + "=" * 80)
    print("NEXT STEPS:")
    print("=" * 80)

    if gh_status.get('deployment_ready'):
        print("✓ GitHub Actions CI passed - Terraform deployment should proceed")
        print("  Monitor: gh run list --repo argie33/algo --branch main")
    else:
        print("⏳ Waiting for GitHub Actions CI to pass")
        print("  Current CI status: {ch_status.get('ci', 'checking...')}")

    print("\nOnce Terraform deployment completes (~10-20 min):")
    print("  1. python3 scripts/trigger_orchestrator.py")
    print("     → Test if credentials fix is deployed")
    print("  2. Check logs: aws logs tail /aws/lambda/algo-algo-dev --follow")
    print("     → Look for: '[CREDENTIALS] Found credentials in algo-algo-secrets-dev'")
    print("  3. If successful: python3 scripts/trigger_computed_metrics_pipeline.py")
    print("     → Refresh value_metrics with fresh market_exposure data")


if __name__ == "__main__":
    main()
