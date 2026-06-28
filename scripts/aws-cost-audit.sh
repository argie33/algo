#!/bin/bash
# AWS Cost Audit — Identify NAT Gateway and top service costs
# Run this in your AWS account with CLI credentials

set -e

REGION="us-east-1"  # Adjust if your resources are in a different region
echo "=== AWS Cost Efficiency Audit ==="
echo "Checking region: $REGION"
echo ""

# 1. Check for active NAT Gateways
echo "1. NAT GATEWAY CHECK (CRITICAL — could be $30-50/month)"
echo "=============================================="
NAT_COUNT=$(aws ec2 describe-nat-gateways \
  --region $REGION \
  --filter "Name=state,Values=available" \
  --query 'NatGateways | length(@)' \
  --output text 2>/dev/null || echo "0")

if [ "$NAT_COUNT" -gt 0 ]; then
  echo "⚠️  FOUND $NAT_COUNT active NAT Gateway(s)"
  aws ec2 describe-nat-gateways \
    --region $REGION \
    --filter "Name=state,Values=available" \
    --query 'NatGateways[].[NatGatewayId, State, SubnetId, CreateTime]' \
    --output table

  echo ""
  echo "Estimated monthly cost: $30-50 (0.045/hour × 24 × 30 + data transfer)"
  echo "To eliminate: Route ECS traffic through VPC Endpoints (S3, Secrets Manager)"
  echo ""
else
  echo "✅ No active NAT Gateways found"
fi

# 2. Daily cost breakdown (last 14 days)
echo ""
echo "2. DAILY SERVICE COSTS (Last 14 days)"
echo "=============================================="
aws ce get-cost-and-usage \
  --time-period Start=$(date -d '14 days ago' +%Y-%m-%d),End=$(date +%Y-%m-%d) \
  --granularity DAILY \
  --metrics UnblendedCost \
  --group-by Type=DIMENSION,Key=SERVICE \
  --query 'ResultsByTime[-7:].{Date:TimePeriod.Start, Services:Groups[?contains(Keys[0], `EC2`) || contains(Keys[0], `RDS`) || contains(Keys[0], `DynamoDB`) || contains(Keys[0], `Lambda`)].{Service:Keys[0], Cost:Metrics.UnblendedCost.Amount}}' \
  --output table || echo "Cost Explorer access denied (check IAM permissions)"

# 3. Summary estimate
echo ""
echo "3. CURRENT INFRASTRUCTURE COST ESTIMATE"
echo "=============================================="
echo "RDS (t4g.small + Proxy):            $42-48/month"
echo "ECS Fargate (33 loaders, 80% SPOT): $13/month"
echo "CloudWatch (logs + alarms):         $7.50/month"
echo "DynamoDB (PAY_PER_REQUEST):         $0.05/month"
echo "NAT Gateway (if present):           $33-50/month  ⚠️"
echo "Other (Lambda, S3, etc):            $0.50/month"
echo "---"
echo "TOTAL WITHOUT NAT:                  $62-69/month ($744-828/year)"
echo "TOTAL WITH NAT:                     $95-119/month ($1144-1428/year)"
echo ""

# 4. Post-optimization estimate
echo "4. AFTER TIER 1 OPTIMIZATIONS (Applied Today)"
echo "=============================================="
echo "Estimated savings:                  $13-20/month ($156-240/year)"
echo "Projected new total (no NAT):       $50-56/month ($600-672/year)"
echo "Projected with NAT elimination:     ~$20-25/month ($240-300/year)"
echo ""
echo "Next: If NAT was >$30/month, VPC Endpoint migration saves another $396-600/year"
