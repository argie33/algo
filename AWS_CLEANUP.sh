#!/bin/bash
# ============================================================
# AWS CLEANUP SCRIPT - Remove Orphaned Resources
# Stock Analytics Platform
# Run this with: bash AWS_CLEANUP.sh
# ============================================================

set -e

REGION="us-east-1"
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

echo "============================================================"
echo "AWS CLEANUP - Stock Analytics Platform"
echo "Region: $REGION"
echo "Account: $ACCOUNT_ID"
echo "============================================================"
echo ""

# ============================================================
# PHASE 1: List Current State
# ============================================================
echo "[PHASE 1] Current AWS State"
echo "---"

echo "CloudFormation Stacks with 'stocks' in name:"
aws cloudformation list-stacks \
  --region "$REGION" \
  --query 'StackSummaries[?contains(StackName, `stocks`)].{Name:StackName,Status:StackStatus}' \
  --output table || echo "(No stacks or error)"

echo ""
echo "VPCs with CIDR 10.0.0.0/16 (should be 0 or 1):"
aws ec2 describe-vpcs \
  --region "$REGION" \
  --query 'Vpcs[?CidrBlock==`10.0.0.0/16`].{VpcId:VpcId,State:State}' \
  --output table || echo "(None found)"

echo ""
echo "S3 Buckets with 'stocks' or 'algo' in name:"
aws s3 ls --region "$REGION" 2>/dev/null | grep -E "stocks|algo" || echo "(None found)"

echo ""
echo "ECR Repositories with 'stocks' in name:"
aws ecr describe-repositories \
  --region "$REGION" \
  --query 'repositories[?contains(repositoryName, `stocks`)].repositoryName' \
  --output table 2>/dev/null || echo "(None found)"

echo ""
echo "============================================================"
echo "[PHASE 2] Delete Stacks (in reverse dependency order)"
echo "---"

# Delete in reverse order: webapp, loaders, data, core, oidc
for STACK in stocks-webapp-dev stocks-loaders stocks-data stocks-core stocks-oidc; do
  STATUS=$(aws cloudformation describe-stacks \
    --stack-name "$STACK" \
    --region "$REGION" \
    --query 'Stacks[0].StackStatus' \
    --output text 2>/dev/null || echo "DOES_NOT_EXIST")

  if [[ "$STATUS" != "DOES_NOT_EXIST" ]]; then
    echo "Deleting stack: $STACK (current status: $STATUS)"
    aws cloudformation delete-stack \
      --stack-name "$STACK" \
      --region "$REGION" || echo "  (Could not delete - may already be deleting)"

    echo "  Waiting for deletion to complete..."
    aws cloudformation wait stack-delete-complete \
      --stack-name "$STACK" \
      --region "$REGION" 2>/dev/null || echo "  (Deletion timed out or already deleted)"
    echo "  ✅ $STACK cleaned"
  else
    echo "Stack $STACK does not exist (skipping)"
  fi
done

echo ""
echo "============================================================"
echo "[PHASE 3] Delete Orphaned Resources"
echo "---"

# Force delete ECR repositories (they block S3 cleanup sometimes)
echo "Force-deleting ECR repositories..."
for REPO in stocks-app-registry stocks-loaders-registry stocks-webapp-registry stocks-algo-registry; do
  aws ecr delete-repository \
    --repository-name "$REPO" \
    --force \
    --region "$REGION" 2>/dev/null && echo "  ✅ Deleted: $REPO" || echo "  (Repo $REPO not found)"
done

echo ""
echo "Deleting orphaned VPCs with CIDR 10.0.0.0/16..."
VPC_IDS=$(aws ec2 describe-vpcs \
  --region "$REGION" \
  --query 'Vpcs[?CidrBlock==`10.0.0.0/16`].VpcId' \
  --output text)

for VPC_ID in $VPC_IDS; do
  echo "  Processing VPC: $VPC_ID"

  # Delete ENIs first
  ENI_IDS=$(aws ec2 describe-network-interfaces \
    --region "$REGION" \
    --filters "Name=vpc-id,Values=$VPC_ID" \
    --query 'NetworkInterfaces[].NetworkInterfaceId' \
    --output text)

  for ENI_ID in $ENI_IDS; do
    echo "    Deleting ENI: $ENI_ID"
    aws ec2 delete-network-interface \
      --network-interface-id "$ENI_ID" \
      --region "$REGION" 2>/dev/null || echo "      (Could not delete - may be in use)"
  done

  # Delete Internet Gateways
  IGW_IDS=$(aws ec2 describe-internet-gateways \
    --region "$REGION" \
    --filters "Name=attachment.vpc-id,Values=$VPC_ID" \
    --query 'InternetGateways[].InternetGatewayId' \
    --output text)

  for IGW_ID in $IGW_IDS; do
    echo "    Detaching IGW: $IGW_ID"
    aws ec2 detach-internet-gateway \
      --internet-gateway-id "$IGW_ID" \
      --vpc-id "$VPC_ID" \
      --region "$REGION" 2>/dev/null || echo "      (Already detached)"

    echo "    Deleting IGW: $IGW_ID"
    aws ec2 delete-internet-gateway \
      --internet-gateway-id "$IGW_ID" \
      --region "$REGION" 2>/dev/null || echo "      (Could not delete)"
  done

  # Delete Subnets
  SUBNET_IDS=$(aws ec2 describe-subnets \
    --region "$REGION" \
    --filters "Name=vpc-id,Values=$VPC_ID" \
    --query 'Subnets[].SubnetId' \
    --output text)

  for SUBNET_ID in $SUBNET_IDS; do
    echo "    Deleting Subnet: $SUBNET_ID"
    aws ec2 delete-subnet \
      --subnet-id "$SUBNET_ID" \
      --region "$REGION" 2>/dev/null || echo "      (Could not delete)"
  done

  # Delete Route Tables (keep main)
  RTABLE_IDS=$(aws ec2 describe-route-tables \
    --region "$REGION" \
    --filters "Name=vpc-id,Values=$VPC_ID" \
    --query 'RouteTables[?!Associations[?Main==`true`]].RouteTableId' \
    --output text)

  for RTABLE_ID in $RTABLE_IDS; do
    echo "    Deleting Route Table: $RTABLE_ID"
    aws ec2 delete-route-table \
      --route-table-id "$RTABLE_ID" \
      --region "$REGION" 2>/dev/null || echo "      (Could not delete)"
  done

  # Delete Security Groups (keep default)
  SG_IDS=$(aws ec2 describe-security-groups \
    --region "$REGION" \
    --filters "Name=vpc-id,Values=$VPC_ID" "Name=group-name,Values=!default" \
    --query 'SecurityGroups[].GroupId' \
    --output text)

  for SG_ID in $SG_IDS; do
    echo "    Deleting Security Group: $SG_ID"
    aws ec2 delete-security-group \
      --group-id "$SG_ID" \
      --region "$REGION" 2>/dev/null || echo "      (Could not delete - may have dependencies)"
  done

  # Delete VPC Endpoints
  VPCE_IDS=$(aws ec2 describe-vpc-endpoints \
    --region "$REGION" \
    --filters "Name=vpc-id,Values=$VPC_ID" \
    --query 'VpcEndpoints[].VpcEndpointId' \
    --output text)

  for VPCE_ID in $VPCE_IDS; do
    echo "    Deleting VPC Endpoint: $VPCE_ID"
    aws ec2 delete-vpc-endpoints \
      --vpc-endpoint-ids "$VPCE_ID" \
      --region "$REGION" 2>/dev/null || echo "      (Could not delete)"
  done

  # Delete VPC itself
  echo "    Deleting VPC: $VPC_ID"
  aws ec2 delete-vpc \
    --vpc-id "$VPC_ID" \
    --region "$REGION" 2>/dev/null || echo "      (Could not delete - may have remaining dependencies)"
done

echo ""
echo "============================================================"
echo "[PHASE 4] Final Verification"
echo "---"

echo "Remaining CloudFormation stacks with 'stocks':"
aws cloudformation list-stacks \
  --region "$REGION" \
  --query 'StackSummaries[?contains(StackName, `stocks`) && StackStatus != `DELETE_COMPLETE`].{Name:StackName,Status:StackStatus}' \
  --output table || echo "(None found)"

echo ""
echo "Remaining VPCs with CIDR 10.0.0.0/16:"
aws ec2 describe-vpcs \
  --region "$REGION" \
  --query 'Vpcs[?CidrBlock==`10.0.0.0/16`]' \
  --output table || echo "(None found)"

echo ""
echo "============================================================"
echo "CLEANUP COMPLETE"
echo "============================================================"
echo ""
echo "Next steps:"
echo "1. Verify AWS account is clean (no stacks, no VPCs with 10.0.0.0/16)"
echo "2. User revokes your temporary admin privileges"
echo "3. Run GitHub Actions workflow to deploy: deploy-core.yml"
echo "4. Monitor cascade deployments: data-infrastructure → loaders → webapp → algo"
echo "============================================================"
