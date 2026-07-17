#!/usr/bin/env python3
"""
Comprehensive AWS cost analysis for July 2026.
Requires elevated permissions: ce:GetCostAndUsage, cloudwatch, ecs, rds, lambda, dynamodb, s3
Run via GitHub Actions with proper IAM role.
"""
import boto3
from datetime import datetime, timedelta, timezone
from typing import Dict, List
import json

def get_ce_client():
    """Get Cost Explorer client."""
    return boto3.client('ce', region_name='us-east-1')

def get_eod_date(days_ago=0):
    """Get end-of-day for analysis (today or N days ago)."""
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).strftime('%Y-%m-%d')

def analyze_july_costs():
    """Get daily cost breakdown for July 2026."""
    ce = get_ce_client()

    print("\n" + "="*80)
    print("AWS COST ANALYSIS - JULY 2026")
    print("="*80 + "\n")

    try:
        response = ce.get_cost_and_usage(
            TimePeriod={
                'Start': '2026-07-01',
                'End': '2026-07-18'
            },
            Granularity='DAILY',
            Metrics=['UnblendedCost'],
            GroupBy=[
                {'Type': 'DIMENSION', 'Key': 'SERVICE'}
            ]
        )

        print("DAILY COST BY SERVICE:\n")

        daily_totals = {}
        service_totals = {}

        for result in response['ResultsByTime']:
            date = result['TimePeriod']['Start']
            daily_total = 0

            print(f"\n{date}:")
            for group in result['Groups']:
                service = group['Keys'][0]
                cost = float(group['Metrics']['UnblendedCost']['Amount'])

                if cost > 0.01:  # Only show significant costs
                    print(f"  {service}: ${cost:.2f}")

                daily_total += cost
                service_totals[service] = service_totals.get(service, 0) + cost

            daily_totals[date] = daily_total
            print(f"  DAILY TOTAL: ${daily_total:.2f}")

        print("\n" + "="*80)
        print("SUMMARY BY SERVICE (Cumulative 2026-07-01 to 2026-07-18):\n")

        for service, cost in sorted(service_totals.items(), key=lambda x: x[1], reverse=True):
            if cost > 0.01:
                daily_avg = cost / 17  # 17 days of data
                monthly_proj = (cost / 17) * 31
                print(f"  {service:30s}: ${cost:7.2f}  (avg ${daily_avg:.2f}/day, proj ${monthly_proj:.2f}/month)")

        total_cost = sum(daily_totals.values())
        print(f"\n  {'TOTAL':30s}: ${total_cost:7.2f}  (avg ${total_cost/17:.2f}/day, proj ${(total_cost/17)*31:.2f}/month)")

        return {
            'daily_totals': daily_totals,
            'service_totals': service_totals,
            'total_cost': total_cost,
            'projected_monthly': (total_cost / 17) * 31
        }

    except Exception as e:
        print(f"[ERROR] Cost Explorer access denied: {e}")
        print("-> Run this script via GitHub Actions with proper IAM permissions")
        return None

def analyze_ecs_costs():
    """Estimate ECS Fargate costs based on current configuration."""
    print("\n" + "="*80)
    print("ESTIMATED ECS FARGATE COSTS (Based on Configuration)")
    print("="*80 + "\n")

    # Fargate pricing (us-east-1, on-demand)
    cpu_cost_per_hour = 0.04288  # per vCPU (1024 CPU = 1 vCPU)
    memory_cost_per_hour = 0.004731  # per GB

    # Task definitions from terraform
    tasks = {
        'large': {'cpu': 1024, 'memory': 2048, 'cost_per_hour': (1.0 * cpu_cost_per_hour) + (2.0 * memory_cost_per_hour)},
        'xlarge': {'cpu': 1024, 'memory': 4096, 'cost_per_hour': (1.0 * cpu_cost_per_hour) + (4.0 * memory_cost_per_hour)},
        'medium': {'cpu': 512, 'memory': 1024, 'cost_per_hour': (0.5 * cpu_cost_per_hour) + (1.0 * memory_cost_per_hour)},
        'small': {'cpu': 256, 'memory': 512, 'cost_per_hour': (0.25 * cpu_cost_per_hour) + (0.5 * memory_cost_per_hour)},
    }

    for size, specs in tasks.items():
        hourly = specs['cost_per_hour']
        daily = hourly * 24
        monthly = hourly * 730  # Approximate
        print(f"  {size.upper():8s} ({specs['cpu']:4d}CPU/{specs['memory']:4d}MB): ${hourly:.4f}/hr = ${daily:.2f}/day = ${monthly:.2f}/month")

    print("\n  NOTE: Actual costs depend on:")
    print("    • How many tasks run per day")
    print("    • Task duration and parallelism")
    print("    • Whether tasks fail and retry (cost multiplier)")
    print("    • Reserved Capacity discount (if applicable)")

    return tasks

def analyze_rds_costs():
    """Estimate RDS costs based on current instance."""
    print("\n" + "="*80)
    print("ESTIMATED RDS COSTS")
    print("="*80 + "\n")

    # db.t4g.small pricing (us-east-1, on-demand)
    hourly_rate = 0.042  # Approximate
    daily = hourly_rate * 24
    monthly = hourly_rate * 730

    print(f"  Instance Type: db.t4g.small")
    print(f"  On-Demand Rate: ${hourly_rate:.3f}/hour")
    print(f"  Daily Cost: ${daily:.2f}")
    print(f"  Monthly Cost (projected): ${monthly:.2f}")
    print(f"  Storage (61 GB): ~$6/month")
    print(f"  Backups (automated): ~$6/month")
    print(f"  TOTAL MONTHLY: ~${monthly + 12:.2f}")

def analyze_dynamodb_costs():
    """Show DynamoDB cost structure."""
    print("\n" + "="*80)
    print("DYNAMODB COSTS (Pay-Per-Request)")
    print("="*80 + "\n")

    print("  Billing Mode: PAY_PER_REQUEST")
    print("  Read: $0.25 per million read units")
    print("  Write: $1.25 per million write units")
    print("  ")
    print("  Tables (monitoring only - verify actual usage in CloudWatch):")
    print("    • orchestrator-locks")
    print("    • loader-locks")
    print("    • loader-status")
    print("    • loader-config")
    print("  ")
    print("  Estimated: $2-10/month (light usage during orchestration)")

def analyze_lambda_costs():
    """Show Lambda cost structure."""
    print("\n" + "="*80)
    print("LAMBDA COSTS")
    print("="*80 + "\n")

    print("  Invocations: $0.20 per million invocations")
    print("  Duration: $0.0000166667 per GB-second")
    print("  ")
    print("  Loaders:")
    print("    • loader-failure-handler: Called on ECS task failures")
    print("    • credential_manager: Called by all loaders")
    print("    • Various data processing functions")
    print("  ")
    print("  Estimated: $5-20/month (light invocation volume)")

def main():
    """Run all cost analyses."""

    # Try Cost Explorer (requires elevated IAM)
    print("\n[INFO] Attempting to fetch actual costs from Cost Explorer...")
    costs = analyze_july_costs()

    if costs is None:
        print("\n[INFO] Cost Explorer access denied (expected with developer IAM role)")
        print("[INFO] Using infrastructure cost estimations instead...\n")

    # Show infrastructure estimates
    ecs_costs = analyze_ecs_costs()
    analyze_rds_costs()
    analyze_dynamodb_costs()
    analyze_lambda_costs()

    print("\n" + "="*80)
    print("HOW TO GET FULL BILLING DATA")
    print("="*80 + "\n")

    print("  1. Run this script via GitHub Actions workflow (deploy workflow)")
    print("     → It will use the assumed role with cost:GetCostAndUsage permission")
    print("  ")
    print("  2. Or request billing access from AWS account administrator")
    print("     → Need: ce:GetCostAndUsage permission for full Cost Explorer data")
    print("  ")
    print("  3. Check AWS Console → Billing & Cost Management")
    print("     → Bills tab shows historical invoices")
    print("     → Cost Explorer shows daily/monthly breakdown")
    print("  ")
    print("  4. Set up AWS Budgets for monthly alerts")
    print("     → https://console.aws.amazon.com/billing/")

if __name__ == '__main__':
    main()
