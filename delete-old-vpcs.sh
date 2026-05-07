#!/bin/bash
set -e

REGION="us-east-1"
echo "Deleting orphaned VPCs in $REGION..."
echo ""

# Get all VPCs that are NOT the default VPC
VPC_IDS=$(aws ec2 describe-vpcs \
  --region $REGION \
  --filters "Name=isDefault,Values=false" \
  --query 'Vpcs[*].VpcId' \
  --output text)

if [ -z "$VPC_IDS" ]; then
  echo "No VPCs to delete"
  exit 0
fi

echo "Found VPCs to delete:"
for VPC_ID in $VPC_IDS; do
  CIDR=$(aws ec2 describe-vpcs --vpc-ids $VPC_ID --region $REGION --query 'Vpcs[0].CidrBlock' --output text)
  NAME=$(aws ec2 describe-vpcs --vpc-ids $VPC_ID --region $REGION --query 'Vpcs[0].Tags[?Key==`Name`].Value' --output text || echo "untagged")
  echo "  $VPC_ID ($NAME, $CIDR)"
done

echo ""
echo "This will DELETE all resources in these VPCs:"
echo "  - Subnets"
echo "  - Internet Gateways"
echo "  - Route Tables (non-default)"
echo "  - Security Groups (non-default)"
echo "  - VPCs"
echo ""
read -p "Type 'DELETE' to confirm: " CONFIRM

if [ "$CONFIRM" != "DELETE" ]; then
  echo "Cancelled"
  exit 0
fi

for VPC_ID in $VPC_IDS; do
  echo ""
  echo "Deleting VPC: $VPC_ID"

  # Delete subnets
  echo "  Deleting subnets..."
  SUBNET_IDS=$(aws ec2 describe-subnets --filters "Name=vpc-id,Values=$VPC_ID" --region $REGION --query 'Subnets[*].SubnetId' --output text)
  for SUBNET_ID in $SUBNET_IDS; do
    aws ec2 delete-subnet --subnet-id $SUBNET_ID --region $REGION 2>/dev/null || true
  done

  # Detach and delete internet gateways
  echo "  Deleting internet gateways..."
  IGW_IDS=$(aws ec2 describe-internet-gateways --filters "Name=attachment.vpc-id,Values=$VPC_ID" --region $REGION --query 'InternetGateways[*].InternetGatewayId' --output text)
  for IGW_ID in $IGW_IDS; do
    aws ec2 detach-internet-gateway --internet-gateway-id $IGW_ID --vpc-id $VPC_ID --region $REGION 2>/dev/null || true
    aws ec2 delete-internet-gateway --internet-gateway-id $IGW_ID --region $REGION 2>/dev/null || true
  done

  # Delete non-default route tables
  echo "  Deleting route tables..."
  RT_IDS=$(aws ec2 describe-route-tables --filters "Name=vpc-id,Values=$VPC_ID" "Name=association.main,Values=false" --region $REGION --query 'RouteTables[*].RouteTableId' --output text)
  for RT_ID in $RT_IDS; do
    aws ec2 delete-route-table --route-table-id $RT_ID --region $REGION 2>/dev/null || true
  done

  # Delete non-default security groups
  echo "  Deleting security groups..."
  SG_IDS=$(aws ec2 describe-security-groups --filters "Name=vpc-id,Values=$VPC_ID" "Name=group-name,Values=!default" --region $REGION --query 'SecurityGroups[*].GroupId' --output text)
  for SG_ID in $SG_IDS; do
    aws ec2 delete-security-group --group-id $SG_ID --region $REGION 2>/dev/null || true
  done

  # Delete VPC
  echo "  Deleting VPC..."
  aws ec2 delete-vpc --vpc-id $VPC_ID --region $REGION
  echo "  ✓ Deleted $VPC_ID"
done

echo ""
echo "✅ All orphaned VPCs deleted"
echo ""

# Verify
VPC_COUNT=$(aws ec2 describe-vpcs --region $REGION --query 'length(Vpcs)' --output text)
echo "Current VPC count: $VPC_COUNT/5"
