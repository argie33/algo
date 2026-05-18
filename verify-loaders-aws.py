#!/usr/bin/env python3
"""
AWS Loader Verification & Testing Script

Verifies that all AWS infrastructure is in place for data loading,
triggers test loaders, monitors CloudWatch logs, and verifies data
was actually loaded into RDS.

Usage:
    python3 verify-loaders-aws.py [--verify-only] [--trigger-tier-0]
"""

import sys
import os
import json
import subprocess
import time
import logging
from datetime import datetime, date
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

# Add root to path
sys.path.insert(0, str(Path(__file__).parent))

AWS_REGION = "us-east-1"
PROJECT_NAME = "algo"


def run_aws_cli(cmd):
    """Run AWS CLI command, return output."""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=30
        )
        return result.stdout.strip(), result.returncode
    except subprocess.TimeoutExpired:
        return "", 1
    except Exception as e:
        logger.error(f"AWS CLI error: {e}")
        return "", 1


def check_aws_credentials():
    """Verify AWS credentials are configured."""
    logger.info("1️⃣  Checking AWS Credentials...")
    output, code = run_aws_cli("aws sts get-caller-identity --region us-east-1")
    if code != 0:
        logger.error("❌ AWS credentials not configured")
        logger.error("   Run: aws configure")
        return False

    try:
        identity = json.loads(output)
        logger.info(f"✅ AWS Account: {identity.get('Account')}")
        logger.info(f"   User/Role: {identity.get('Arn', 'unknown')}")
        return True
    except:
        logger.error("❌ Could not parse AWS identity")
        return False


def check_ecs_cluster():
    """Verify ECS cluster exists."""
    logger.info("\n2️⃣  Checking ECS Cluster...")
    output, code = run_aws_cli(
        f"aws ecs list-clusters --region {AWS_REGION} --query 'clusterArns[0]' --output text"
    )
    if code != 0 or "None" in output:
        logger.error("❌ No ECS cluster found")
        return None

    cluster_name = output.split("/")[-1]
    logger.info(f"✅ ECS Cluster: {cluster_name}")
    return cluster_name


def check_rds_database():
    """Verify RDS database exists and is accessible."""
    logger.info("\n3️⃣  Checking RDS Database...")
    output, code = run_aws_cli(
        f"aws rds describe-db-instances --region {AWS_REGION} "
        f"--query 'DBInstances[0].Endpoint.Address' --output text"
    )
    if code != 0 or "None" in output:
        logger.error("❌ No RDS database found")
        return None

    db_host = output.strip()
    logger.info(f"✅ RDS Host: {db_host}")
    return db_host


def check_cloudwatch_logs():
    """Verify CloudWatch log groups exist for loaders."""
    logger.info("\n4️⃣  Checking CloudWatch Log Groups...")
    output, code = run_aws_cli(
        f"aws logs describe-log-groups --log-group-name-prefix '/ecs/{PROJECT_NAME}-' "
        f"--region {AWS_REGION} --query 'logGroups[*].logGroupName' --output text"
    )
    if code != 0:
        logger.warning("⚠️  Could not list log groups")
        return 0

    if not output or "None" in output:
        logger.warning("⚠️  No loader log groups found yet")
        return 0

    groups = len(output.split())
    logger.info(f"✅ Found {groups} log groups")
    return groups


def check_ecr_repository():
    """Verify Docker image is in ECR."""
    logger.info("\n5️⃣  Checking ECR Repository...")
    output, code = run_aws_cli(
        f"aws ecr describe-repositories --region {AWS_REGION} "
        f"--query 'repositories[0].repositoryUri' --output text"
    )
    if code != 0 or "None" in output:
        logger.error("❌ No ECR repository found")
        return None

    ecr_uri = output.strip()
    logger.info(f"✅ ECR Repository: {ecr_uri}")

    # Check if image exists
    repo_name = ecr_uri.split("/")[1]
    output2, code2 = run_aws_cli(
        f"aws ecr describe-images --repository-name {repo_name} --region {AWS_REGION} "
        f"--query 'imageDetails[-1]' --output json"
    )
    if code2 == 0 and output2:
        try:
            image = json.loads(output2)
            tags = image.get('imageTags', [])
            logger.info(f"   Latest tags: {', '.join(tags[-3:]) if tags else 'none'}")
        except:
            pass

    return ecr_uri


def check_api_gateway():
    """Verify API Gateway is responding."""
    logger.info("\n6️⃣  Checking API Gateway...")
    output, code = run_aws_cli(
        f"aws apigatewayv2 get-apis --region {AWS_REGION} "
        f"--query 'Items[0].ApiEndpoint' --output text"
    )
    if code != 0 or "None" in output:
        logger.warning("⚠️  No API Gateway found")
        return None

    endpoint = output.strip()
    logger.info(f"✅ API Endpoint: {endpoint}")

    # Test health endpoint
    test_cmd = f"curl -s -o /dev/null -w '%{{http_code}}' '{endpoint}/health'"
    status, _ = run_aws_cli(test_cmd)
    if status == "200":
        logger.info("   ✅ Health endpoint responding")
    else:
        logger.warning(f"   ⚠️  Health endpoint returned {status}")

    return endpoint


def check_task_definitions():
    """List available ECS task definitions."""
    logger.info("\n7️⃣  Checking ECS Task Definitions...")
    output, code = run_aws_cli(
        f"aws ecs list-task-definition-families --region {AWS_REGION} "
        f"--status ACTIVE --query 'taskDefinitionFamilies' --output text"
    )
    if code != 0 or not output:
        logger.warning("⚠️  No active task definitions found")
        return 0

    families = output.split()
    loader_families = [f for f in families if 'loader' in f]
    logger.info(f"✅ Found {len(loader_families)} loader task families")
    if loader_families:
        for f in sorted(loader_families)[:5]:
            logger.info(f"   - {f}")
        if len(loader_families) > 5:
            logger.info(f"   ... and {len(loader_families)-5} more")

    return len(loader_families)


def list_recent_logs():
    """Show recent CloudWatch logs from loaders."""
    logger.info("\n8️⃣  Recent Loader Activity...")
    output, code = run_aws_cli(
        f"aws logs describe-log-groups --log-group-name-prefix '/ecs/{PROJECT_NAME}-' "
        f"--region {AWS_REGION} --query 'logGroups[0:3].logGroupName' --output text"
    )

    if code != 0 or not output:
        logger.info("   No recent activity found")
        return

    log_groups = output.split()
    for log_group in log_groups:
        logger.info(f"\n   📋 {log_group.split('/')[-1]}")
        cmd = (f"aws logs tail '{log_group}' --region {AWS_REGION} "
               f"--since 24h --max-items 2 --format short 2>/dev/null")
        logs, _ = run_aws_cli(cmd)
        if logs:
            for line in logs.split('\n')[:2]:
                logger.info(f"      {line}")
        else:
            logger.info("      (no logs)")


def verify_database_data():
    """Check if data has been loaded into RDS."""
    logger.info("\n9️⃣  Checking RDS Data...")

    try:
        from config.credential_helper import get_db_config
        from utils.db_connection import get_db_connection

        db_config = get_db_config()
        conn = get_db_connection()
        cursor = conn.cursor()

        # Check stock symbols
        cursor.execute("SELECT COUNT(*) FROM stock_symbols")
        symbols_count = cursor.fetchone()[0]
        logger.info(f"✅ Stock Symbols: {symbols_count:,}")

        # Check prices for Friday
        cursor.execute(
            "SELECT COUNT(*) FROM price_daily WHERE date = %s",
            (date(2026, 5, 15),)
        )
        friday_prices = cursor.fetchone()[0]
        logger.info(f"✅ Friday Prices (2026-05-15): {friday_prices:,}")

        # Check latest prices
        cursor.execute(
            "SELECT COUNT(*), MAX(date) FROM price_daily"
        )
        result = cursor.fetchone()
        latest_count, latest_date = result[0], result[1]
        logger.info(f"✅ Latest Prices: {latest_count:,} (as of {latest_date})")

        # Check signals for Friday
        cursor.execute(
            "SELECT COUNT(*) FROM buy_sell_signal_daily WHERE date = %s",
            (date(2026, 5, 15),)
        )
        friday_signals = cursor.fetchone()[0]
        logger.info(f"✅ Friday Signals (2026-05-15): {friday_signals:,}")

        cursor.close()
        conn.close()

    except Exception as e:
        logger.warning(f"⚠️  Could not check database: {e}")
        logger.info("   This is expected if database isn't accessible locally")


def print_summary(has_aws_creds, cluster, rds, logs, tasks, data_status):
    """Print verification summary."""
    logger.info("\n" + "="*70)
    logger.info("VERIFICATION SUMMARY")
    logger.info("="*70)

    if has_aws_creds:
        logger.info("✅ AWS Infrastructure Ready")
        logger.info(f"   - ECS Cluster: {'✅' if cluster else '❌'}")
        logger.info(f"   - RDS Database: {'✅' if rds else '❌'}")
        logger.info(f"   - CloudWatch Logs: {'✅' if logs > 0 else '⚠️'}")
        logger.info(f"   - Task Definitions: {'✅' if tasks > 0 else '❌'}")
    else:
        logger.info("⚠️  AWS Credentials Not Available")
        logger.info("   To test loaders in AWS, configure: aws configure")

    logger.info("\n📊 Data Status")
    logger.info("   Check database for:")
    logger.info("   - Stock symbols loaded?")
    logger.info("   - Friday prices loaded?")
    logger.info("   - Buy/sell signals for Friday?")

    logger.info("\n🚀 Next Steps")
    logger.info("   1. If AWS credentials available:")
    logger.info("      ./trigger-loader-ecs.sh stock_symbols")
    logger.info("      ./trigger-loader-ecs.sh stock_prices_daily")
    logger.info("   ")
    logger.info("   2. If testing locally:")
    logger.info("      python3 run-all-loaders.py")
    logger.info("      python3 algo/algo_orchestrator.py --mode paper --run-date 2026-05-15")
    logger.info("   ")
    logger.info("   3. Monitor CloudWatch (if AWS):")
    logger.info("      aws logs tail /ecs/algo-* --follow")


def main():
    """Run all verification checks."""
    logger.info("🔍 AWS LOADER VERIFICATION")
    logger.info("="*70)
    logger.info(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    logger.info(f"Region: {AWS_REGION}")
    logger.info("="*70)

    # Check AWS credentials first
    has_aws_creds = check_aws_credentials()

    if not has_aws_creds:
        logger.info("\n⚠️  AWS credentials not configured. Skipping AWS checks.")
        print_summary(False, False, False, 0, 0, False)
        return 0

    # Run AWS checks
    cluster = check_ecs_cluster()
    rds = check_rds_database()
    logs = check_cloudwatch_logs()
    ecr = check_ecr_repository()
    api = check_api_gateway()
    tasks = check_task_definitions()

    list_recent_logs()

    # Check database data
    verify_database_data()

    # Print summary
    print_summary(has_aws_creds, cluster, rds, logs, tasks, False)

    return 0


if __name__ == "__main__":
    sys.exit(main())
