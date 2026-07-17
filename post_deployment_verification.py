#!/usr/bin/env python3
"""
Post-Deployment Verification Script
Run AFTER GitHub Actions Terraform deployment completes.

Steps:
1. Verify Lambda was updated with credentials fix
2. Trigger test orchestrator run
3. Monitor CloudWatch logs for credential loading
4. If successful: Trigger computed metrics pipeline
5. Monitor data refresh completion
"""

import subprocess
import json
import sys
import time
import os
from datetime import datetime


def run_command(cmd, description):
    """Run a shell command and report results."""
    print(f"\n{'=' * 70}")
    print(f"{description}")
    print(f"{'=' * 70}")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.stdout:
        print(result.stdout[:500])  # First 500 chars
    if result.returncode != 0 and result.stderr:
        print(f"ERROR: {result.stderr[:500]}")
    return result.returncode == 0


def check_terraform_deployment_complete():
    """Check if Terraform deployment is complete."""
    result = subprocess.run(
        ["gh", "run", "list", "--repo", "argie33/algo", "--branch", "main", "--limit", "10",
         "--json", "name,status,conclusion"],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        return False, "Failed to check GitHub Actions"

    runs = json.loads(result.stdout)

    for run in runs:
        if "Terraform" in run["name"]:
            if run["status"] == "completed":
                if run.get("conclusion") == "success":
                    return True, "Terraform deployment succeeded"
                else:
                    return False, f"Terraform deployment {run.get('conclusion')}"
            else:
                return False, f"Terraform still {run['status']}"

    return False, "Terraform deployment not found in runs"


def trigger_orchestrator_test():
    """Trigger an orchestrator run to test credentials fix."""
    print("\n" + "=" * 70)
    print("TRIGGERING TEST ORCHESTRATOR RUN")
    print("=" * 70)

    result = subprocess.run(
        ["python3", "scripts/trigger_orchestrator.py", "--mode", "paper"],
        capture_output=True,
        text=True
    )

    if result.returncode == 0:
        print("Orchestrator triggered successfully")
        print(result.stdout)
        return True
    else:
        print(f"ERROR triggering orchestrator: {result.stderr}")
        return False


def check_lambda_logs_for_credentials():
    """Check CloudWatch logs for credential loading."""
    print("\n" + "=" * 70)
    print("CHECKING LAMBDA LOGS FOR CREDENTIALS")
    print("=" * 70)
    print("Running: aws logs tail /aws/lambda/algo-algo-dev --follow")
    print("Watch for:")
    print("  SUCCESS: '[CREDENTIALS] Found credentials in algo-algo-secrets-dev'")
    print("  ERROR: '[PHASE 8 CRITICAL] Alpaca credentials not available'")
    print("\nYou can also check manually:")
    print("  aws logs tail /aws/lambda/algo-algo-dev --follow")
    print("  (Ctrl+C to stop)")

    # Just show how to check, don't block
    result = subprocess.run(
        ["aws", "logs", "tail", "/aws/lambda/algo-algo-dev", "--max-items", "20"],
        capture_output=True,
        text=True,
        timeout=5
    )

    if "Found credentials in" in result.stdout:
        print("\n✓ Credentials loading successfully!")
        return True
    elif "credentials not available" in result.stdout or "CRITICAL" in result.stdout:
        print("\n✗ Credentials still not available")
        return False
    else:
        print("\n? Could not determine credentials status from logs")
        print("Latest log lines:")
        print(result.stdout[-500:] if result.stdout else "No output")
        return None


def trigger_computed_metrics_pipeline():
    """Trigger refresh of value_metrics and other computed metrics."""
    print("\n" + "=" * 70)
    print("TRIGGERING COMPUTED METRICS PIPELINE")
    print("=" * 70)
    print("Running: python3 scripts/trigger_computed_metrics_pipeline.py")

    result = subprocess.run(
        ["python3", "scripts/trigger_computed_metrics_pipeline.py"],
        capture_output=True,
        text=True
    )

    if result.returncode == 0:
        print("Computed metrics pipeline triggered")
        print(result.stdout)
        return True
    else:
        print(f"ERROR: {result.stderr}")
        return False


def check_value_metrics_freshness():
    """Check if value_metrics has been updated."""
    print("\n" + "=" * 70)
    print("CHECKING VALUE METRICS FRESHNESS")
    print("=" * 70)

    try:
        import psycopg2

        conn = psycopg2.connect(
            dbname='stocks',
            user='stocks',
            host='localhost',
            password=os.environ.get('STOCKS_DB_PASSWORD', ''),
            port=5432
        )
        cur = conn.cursor()

        cur.execute("""
            SELECT MAX(date), CURRENT_DATE - MAX(date) as days_old
            FROM value_metrics
        """)
        result = cur.fetchone()

        if result:
            latest_date, days_old = result
            print(f"Value Metrics: {latest_date} ({days_old} days old)")

            if days_old <= 1:
                print("✓ Value metrics are fresh!")
                return True
            else:
                print(f"✗ Value metrics still stale ({days_old} days)")
                return False

        cur.close()
        conn.close()

    except Exception as e:
        print(f"Error checking database: {e}")
        return None


def main():
    print("\n" + "=" * 70)
    print("POST-DEPLOYMENT VERIFICATION")
    print("=" * 70)
    print(f"Started: {datetime.now().isoformat()}")

    # Step 1: Verify deployment complete
    print("\nSTEP 1: Verifying Terraform Deployment")
    complete, message = check_terraform_deployment_complete()
    if not complete:
        print(f"\n✗ {message}")
        print("\nWaiting for Terraform deployment to complete...")
        print("Check status: gh run list --repo argie33/algo --branch main")
        return 1

    print(f"\n✓ {message}")
    print("Proceeding with verification...")

    # Step 2: Trigger test run
    print("\nSTEP 2: Testing Credentials Fix")
    if not trigger_orchestrator_test():
        print("Failed to trigger orchestrator")
        return 1

    # Wait a moment for Lambda to execute
    print("\nWaiting 10 seconds for Lambda to execute...")
    time.sleep(10)

    # Step 3: Check logs
    print("\nSTEP 3: Checking Lambda Logs")
    credentials_ok = check_lambda_logs_for_credentials()

    if credentials_ok is False:
        print("\nCredentials still not deployed. Waiting for Lambda update...")
        return 1

    if credentials_ok is True:
        print("\n✓ Credentials fix is working!")

        # Step 4: Trigger metrics refresh
        print("\nSTEP 4: Triggering Data Refresh")
        if trigger_computed_metrics_pipeline():
            print("\n✓ Computed metrics pipeline triggered")
            print("This will take 30-120 minutes to complete.")

            # Step 5: Final verification
            print("\nSTEP 5: Check Completion")
            print("In 2+ hours, run:")
            print("  python3 post_deployment_verification.py --check-final")
            print("\nOr check manually:")
            print("  SELECT MAX(date) FROM value_metrics;  -- Should be today")
            print("  SELECT COUNT(*) FILTER (WHERE value_score IS NOT NULL) * 100.0 / COUNT(*)")
            print("    FROM stock_scores;  -- Should be 80%+")

    print("\n" + "=" * 70)
    print("VERIFICATION COMPLETE")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    sys.exit(main())
