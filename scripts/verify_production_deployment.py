#!/usr/bin/env python3
"""Comprehensive AWS production-deployment readiness check.

Built 2026-08-31 (pre-real-money /goal audit) specifically so that once someone with real AWS
IAM admin access fixes the OIDC trust-policy deadlock (see
steering/AWS_OIDC_TRUST_POLICY_RECOVERY.md), verifying the rest of the production deployment is
a single command instead of manually re-deriving each check under pressure. This script requires
real AWS credentials (the local sandbox this was written in has none - confirmed via
`aws sts get-caller-identity` failing against both the default profile and the locally-stored
`algo-developer` profile) - it cannot be run or its output predicted from a repo-only session.

Complements scripts/verify_live_trading_readiness.py (Alpaca credentials + local DB config,
no AWS access needed) - this script covers the AWS infrastructure side that one doesn't.

Checks, all read-only:
  1. GitHub Actions OIDC trust policy on the algo-svc-github-actions-<env> role matches what
     terraform/modules/iam/main.tf expects (repo:argie33/algo:ref:refs/heads/main).
  2. The 4 production API endpoints actually return data (not the 404s directly observed
     2026-08-31 - see ci_cd_deploy_broken_39_days_confirmed_20260824 memory).
  3. Lambda function last-modified timestamp - how stale is what's actually running.
  4. RDS instance DR settings (Multi-AZ, backup retention, deletion protection) match what
     terraform/prod.tfvars declares (Multi-AZ=true, 30-day retention, protection=true).
  5. EventBridge schedules enabled/disabled state matches prod.tfvars's enable_*_orchestrator
     flags (only the 9:30 AM morning run + its prewarm should be ENABLED).
  6. Most recent GitHub Actions run status for the 4 AWS-touching workflows (via `gh`, no AWS
     credentials needed for this one check).

Usage:
  python scripts/verify_production_deployment.py
  python scripts/verify_production_deployment.py --environment prod --project algo
"""

import argparse
import json
import shutil
import subprocess
import sys
from typing import Any

# Matches terraform/prod.tfvars and terraform/variables.tf's github_repository default.
GITHUB_REPO = "argie33/algo"
EXPECTED_TRUST_SUB = f"repo:{GITHUB_REPO}:ref:refs/heads/main"

# The 4 endpoints directly confirmed returning 404 on 2026-08-31 - see
# ci_cd_deploy_broken_39_days_confirmed_20260824 memory for the exact curl output.
API_BASE_URL = "https://2iqq1qhltj.execute-api.us-east-1.amazonaws.com"
API_ENDPOINTS_TO_CHECK = ["/", "/health", "/api/health", "/api/scores?limit=1"]

# From terraform/prod.tfvars - keep in sync if that file changes.
EXPECTED_RDS_MULTI_AZ = True
EXPECTED_RDS_BACKUP_RETENTION_DAYS = 30
EXPECTED_RDS_DELETION_PROTECTION = True
EXPECTED_ENABLED_SCHEDULES = {
    # name_suffix -> should be ENABLED
    "algo-schedule-prewarm-morning": True,
    "algo-schedule-prewarm-afternoon": False,  # only exists if enable_afternoon_orchestrator
}

GH_WORKFLOWS_TO_CHECK = [
    "validate-secrets.yml",
    "trigger-orchestrator-scheduled.yml",
    "deploy-all-infrastructure.yml",
    "deploy-ecs-image.yml",
]


def run_aws_cli(args: list[str]) -> dict[str, Any] | None:
    """Run AWS CLI command, return parsed JSON or None if the resource doesn't exist.

    Mirrors verify_eventbridge_scheduler.py's run_aws_cli() exactly - same Windows PATHEXT
    gotcha (aws.cmd/aws.exe won't resolve via subprocess.run without shutil.which), same
    ResourceNotFoundException-means-None convention.
    """
    aws_path = shutil.which("aws") or "aws"
    try:
        result = subprocess.run([aws_path, *args], capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            return json.loads(result.stdout) if result.stdout else {}
        elif "ResourceNotFoundException" in result.stderr or "NoSuchEntity" in result.stderr:
            return None
        else:
            print(f"    [CLI ERROR] {' '.join(args[:2])}: {result.stderr.strip()[:300]}")
            return {"_cli_error": result.stderr}
    except FileNotFoundError:
        print("    [FAIL] AWS CLI not installed. Install with: pip install awscli")
        return {"_cli_error": "AWS CLI not found on PATH"}
    except subprocess.TimeoutExpired:
        print(f"    [FAIL] AWS CLI call timed out: {' '.join(args[:2])}")
        return {"_cli_error": "timeout"}
    except Exception as e:
        print(f"    [FAIL] {' '.join(args[:2])}: {e}")
        return {"_cli_error": str(e)}


def check_oidc_trust_policy(project: str, environment: str) -> list[str]:
    role_name = f"{project}-svc-github-actions-{environment}"
    print(f"\n[1] OIDC trust policy on role '{role_name}'...")
    result = run_aws_cli(["iam", "get-role", "--role-name", role_name])
    if result is None:
        return [f"  Role '{role_name}' does not exist - check the role name/environment"]
    if result.get("_cli_error"):
        return [f"  Could not fetch role: {result['_cli_error'][:200]}"]

    policy = result.get("Role", {}).get("AssumeRolePolicyDocument", {})
    statements = policy.get("Statement", [])
    for stmt in statements:
        sub_values = stmt.get("Condition", {}).get("StringEquals", {}).get("token.actions.githubusercontent.com:sub")
        if sub_values is None:
            continue
        if sub_values == EXPECTED_TRUST_SUB or (isinstance(sub_values, list) and EXPECTED_TRUST_SUB in sub_values):
            print(f"    OK - trust condition matches: {EXPECTED_TRUST_SUB!r}")
            return []
        print(f"    MISMATCH - trust condition is {sub_values!r}, expected {EXPECTED_TRUST_SUB!r}")
        return [
            f"  Role '{role_name}' trust policy sub condition is {sub_values!r}, "
            f"expected {EXPECTED_TRUST_SUB!r} - see steering/AWS_OIDC_TRUST_POLICY_RECOVERY.md"
        ]
    return [f"  Role '{role_name}' has no OIDC sub condition at all - see steering/AWS_OIDC_TRUST_POLICY_RECOVERY.md"]


def check_api_endpoints() -> list[str]:
    print(f"\n[2] Production API endpoints ({API_BASE_URL})...")
    try:
        import requests
    except ImportError:
        return ["  requests library not available - pip install requests"]

    failures = []
    for path in API_ENDPOINTS_TO_CHECK:
        url = f"{API_BASE_URL}{path}"
        try:
            resp = requests.get(url, timeout=15)
        except requests.RequestException as e:
            failures.append(f"  {path}: request failed - {type(e).__name__}: {e!s:.150}")
            print(f"    FAIL {path}: {type(e).__name__}")
            continue
        if resp.status_code == 404:
            failures.append(f"  {path}: HTTP 404 - {resp.text[:150]}")
            print(f"    FAIL {path}: HTTP 404")
        elif resp.status_code >= 500:
            failures.append(f"  {path}: HTTP {resp.status_code} (server error) - {resp.text[:150]}")
            print(f"    FAIL {path}: HTTP {resp.status_code}")
        else:
            print(f"    OK   {path}: HTTP {resp.status_code}")
    return failures


def check_lambda_staleness(project: str) -> list[str]:
    print(f"\n[3] Lambda function '{project}' last-modified timestamp...")
    result = run_aws_cli(["lambda", "get-function", "--function-name", project])
    if result is None:
        return [f"  Lambda function '{project}' does not exist"]
    if result.get("_cli_error"):
        return [f"  Could not fetch Lambda config: {result['_cli_error'][:200]}"]
    config = result.get("Configuration", {})
    last_modified = config.get("LastModified", "unknown")
    code_sha = config.get("CodeSha256", "unknown")[:16]
    print(f"    LastModified={last_modified}  CodeSha256={code_sha}...")
    print("    (compare LastModified against `git log -1 --format=%ci` on main to gauge staleness)")
    return []


def check_rds_dr_settings(project: str, environment: str) -> list[str]:
    print("\n[4] RDS disaster-recovery settings vs terraform/prod.tfvars...")
    result = run_aws_cli(["rds", "describe-db-instances"])
    if result is None or result.get("_cli_error"):
        return [f"  Could not list RDS instances: {(result or {}).get('_cli_error', 'no result')}"]
    instances = [i for i in result.get("DBInstances", []) if project in i.get("DBInstanceIdentifier", "").lower()]
    if not instances:
        return [f"  No RDS instance found with '{project}' in its identifier"]

    failures = []
    for inst in instances:
        ident = inst.get("DBInstanceIdentifier")
        multi_az = inst.get("MultiAZ")
        retention = inst.get("BackupRetentionPeriod")
        deletion_protection = inst.get("DeletionProtection")
        print(
            f"    {ident}: MultiAZ={multi_az} BackupRetentionDays={retention} DeletionProtection={deletion_protection}"
        )
        if environment == "prod":
            if multi_az != EXPECTED_RDS_MULTI_AZ:
                failures.append(f"  {ident}: MultiAZ={multi_az}, expected {EXPECTED_RDS_MULTI_AZ}")
            if retention != EXPECTED_RDS_BACKUP_RETENTION_DAYS:
                failures.append(
                    f"  {ident}: BackupRetentionPeriod={retention}, expected {EXPECTED_RDS_BACKUP_RETENTION_DAYS}"
                )
            if deletion_protection != EXPECTED_RDS_DELETION_PROTECTION:
                failures.append(
                    f"  {ident}: DeletionProtection={deletion_protection}, expected {EXPECTED_RDS_DELETION_PROTECTION}"
                )
    return failures


def check_eventbridge_schedules(project: str, environment: str) -> list[str]:
    print(f"\n[5] EventBridge Scheduler state (expect ONLY the 9:30 AM morning run enabled, '{environment}')...")
    result = run_aws_cli(["scheduler", "list-schedules", "--name-prefix", f"{project}-algo-schedule"])
    if result is None or result.get("_cli_error"):
        return [f"  Could not list schedules: {(result or {}).get('_cli_error', 'no result')}"]
    schedules = result.get("Schedules", [])
    if not schedules:
        return ["  No schedules found matching the expected name prefix - check the prefix/region"]

    failures = []
    for sched in schedules:
        name = sched.get("Name", "")
        state = sched.get("State", "unknown")
        print(f"    {name}: {state}")
        is_morning_related = "morning" in name.lower()
        is_afternoon_related = "afternoon" in name.lower() or "preclose" in name.lower()
        if is_afternoon_related and state == "ENABLED":
            failures.append(
                f"  {name} is ENABLED but terraform/prod.tfvars has "
                f"enable_afternoon_orchestrator/enable_preclose_orchestrator = false - drift"
            )
        if is_morning_related and state != "ENABLED":
            failures.append(f"  {name} is {state}, expected ENABLED per enable_morning_orchestrator=true")
    return failures


def check_github_actions_status() -> list[str]:
    print("\n[6] Most recent run of each AWS-touching GitHub Actions workflow...")
    gh_path = shutil.which("gh")
    if not gh_path:
        return ["  gh CLI not installed - skip, or install from https://cli.github.com"]

    failures = []
    for workflow in GH_WORKFLOWS_TO_CHECK:
        try:
            result = subprocess.run(
                [gh_path, "run", "list", "-R", "argie33/algo", "--workflow", workflow, "--limit", "1"],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except Exception as e:
            failures.append(f"  {workflow}: gh call failed - {e}")
            continue
        line = result.stdout.strip()
        print(f"    {workflow}: {line or '(no runs found)'}")
        if "failure" in line.lower() or "cancelled" in line.lower():
            failures.append(f"  {workflow}: most recent run did not succeed - {line}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description="Comprehensive AWS production-deployment readiness check")
    parser.add_argument("--project", default="algo", help="Terraform project_name (default: algo)")
    parser.add_argument("--environment", default="prod", help="Terraform environment (default: prod)")
    args = parser.parse_args()

    print("\nProduction Deployment Readiness Check")
    print("=" * 70)
    print(f"project={args.project!r} environment={args.environment!r}")
    print("Requires real AWS credentials with at least read access to IAM/Lambda/RDS/Scheduler.")

    all_failures: list[str] = []
    all_failures += check_oidc_trust_policy(args.project, args.environment)
    all_failures += check_api_endpoints()
    all_failures += check_lambda_staleness(args.project)
    all_failures += check_rds_dr_settings(args.project, args.environment)
    all_failures += check_eventbridge_schedules(args.project, args.environment)
    all_failures += check_github_actions_status()

    print("\n" + "=" * 70)
    print("Not covered by this script (run separately):")
    print("  python scripts/verify_live_trading_readiness.py   (Alpaca credentials + local DB config)")
    print("  python scripts/verify_safety_thresholds.py --strict")

    print("\n" + "=" * 70)
    if all_failures:
        print(f"NOT READY — {len(all_failures)} issue(s) found:")
        for f in all_failures:
            print(f)
        return 1
    print("READY — AWS production deployment checks all pass.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
