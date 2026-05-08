#!/bin/bash
# AWS Resource Cleanup Script for Terraform Failures
# THIS SCRIPT DELETES RESOURCES - USE WITH CAUTION!

set -e

AWS_REGION="us-east-1"
PROJECT_NAME="stocks"
ENVIRONMENT="dev"

echo "=========================================="
echo "AWS Resource Cleanup for Terraform"
echo "=========================================="
echo ""
echo "⚠️  WARNING: This will DELETE resources!"
echo "Region: $AWS_REGION"
echo "Project: $PROJECT_NAME"
echo ""
read -p "Press ENTER to continue, or Ctrl+C to cancel: "
echo ""

# Step 1: Backup RDS if exists
echo "Step 1: Creating RDS backup (if DB exists)..."
EXISTING_DB=$(aws rds describe-db-instances \
  --region $AWS_REGION \
  --query "DBInstances[?contains(DBInstanceIdentifier, '$PROJECT_NAME')].DBInstanceIdentifier" \
  --output text 2>/dev/null || echo "")

if [ -n "$EXISTING_DB" ]; then
  echo "Found RDS instance: $EXISTING_DB"
  SNAPSHOT_ID="$PROJECT_NAME-backup-$(date +%s)"
  echo "Creating snapshot: $SNAPSHOT_ID"
  aws rds create-db-snapshot \
    --db-instance-identifier "$EXISTING_DB" \
    --db-snapshot-identifier "$SNAPSHOT_ID" \
    --region $AWS_REGION 2>/dev/null || echo "Snapshot creation started or already exists"
  echo "✓ Snapshot requested (may take a few minutes)"
else
  echo "✓ No existing RDS instance found"
fi

echo ""
echo "Step 2: Deleting RDS instances..."
DBS=$(aws rds describe-db-instances \
  --region $AWS_REGION \
  --query "DBInstances[?contains(DBInstanceIdentifier, '$PROJECT_NAME')].DBInstanceIdentifier" \
  --output text 2>/dev/null || echo "")

if [ -n "$DBS" ]; then
  for db in $DBS; do
    echo "Deleting RDS instance: $db"
    aws rds delete-db-instance \
      --db-instance-identifier "$db" \
      --skip-final-snapshot \
      --region $AWS_REGION 2>/dev/null || echo "Instance may already be deleting"
    echo "✓ RDS delete requested for: $db"
  done
  echo "⏳ Waiting for RDS deletion (this takes ~5 minutes)..."
  sleep 30
else
  echo "✓ No RDS instances to delete"
fi

echo ""
echo "Step 3: Terminating EC2 instances..."
INSTANCES=$(aws ec2 describe-instances \
  --region $AWS_REGION \
  --filters "Name=tag:Project,Values=$PROJECT_NAME" \
  --query "Reservations[*].Instances[*].InstanceId" \
  --output text 2>/dev/null || echo "")

if [ -n "$INSTANCES" ]; then
  for instance in $INSTANCES; do
    echo "Terminating: $instance"
    aws ec2 terminate-instances \
      --instance-ids "$instance" \
      --region $AWS_REGION 2>/dev/null || true
  done
  echo "✓ EC2 termination requested"
else
  echo "✓ No EC2 instances to delete"
fi

echo ""
echo "Step 4: Deleting security groups..."
SG_IDS=$(aws ec2 describe-security-groups \
  --region $AWS_REGION \
  --filters "Name=tag:Project,Values=$PROJECT_NAME" \
  --query "SecurityGroups[?GroupName != 'default'].GroupId" \
  --output text 2>/dev/null || echo "")

if [ -n "$SG_IDS" ]; then
  echo "⏳ Waiting 10s for instances to terminate..."
  sleep 10
  
  for sg in $SG_IDS; do
    echo "Deleting security group: $sg"
    aws ec2 delete-security-group \
      --group-id "$sg" \
      --region $AWS_REGION 2>/dev/null || echo "Could not delete (may be in use)"
  done
  echo "✓ Security group deletion requested"
else
  echo "✓ No security groups to delete"
fi

echo ""
echo "Step 5: Deleting Internet Gateways..."
VPC_IDS=$(aws ec2 describe-vpcs \
  --region $AWS_REGION \
  --filters "Name=tag:Project,Values=$PROJECT_NAME" \
  --query "Vpcs[*].VpcId" \
  --output text 2>/dev/null || echo "")

if [ -n "$VPC_IDS" ]; then
  for vpc_id in $VPC_IDS; do
    IGW_IDS=$(aws ec2 describe-internet-gateways \
      --region $AWS_REGION \
      --filters "Name=attachment.vpc-id,Values=$vpc_id" \
      --query "InternetGateways[*].InternetGatewayId" \
      --output text 2>/dev/null || echo "")
    
    for igw in $IGW_IDS; do
      echo "Detaching IGW: $igw from VPC: $vpc_id"
      aws ec2 detach-internet-gateway \
        --internet-gateway-id "$igw" \
        --vpc-id "$vpc_id" \
        --region $AWS_REGION 2>/dev/null || true
      echo "Deleting IGW: $igw"
      aws ec2 delete-internet-gateway \
        --internet-gateway-id "$igw" \
        --region $AWS_REGION 2>/dev/null || true
    done
  done
  echo "✓ IGW deletion requested"
else
  echo "✓ No VPCs found to clean up"
fi

echo ""
echo "Step 6: Deleting VPCs..."
if [ -n "$VPC_IDS" ]; then
  for vpc_id in $VPC_IDS; do
    echo "Deleting VPC: $vpc_id"
    aws ec2 delete-vpc \
      --vpc-id "$vpc_id" \
      --region $AWS_REGION 2>/dev/null || echo "Could not delete VPC (may still have resources)"
  done
  echo "✓ VPC deletion requested"
fi

echo ""
echo "=========================================="
echo "✓ Cleanup Complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Wait 5+ minutes for RDS and EC2 to fully delete"
echo "2. Run: cd terraform && rm -rf .terraform/"
echo "3. Run: terraform init"
echo "4. Run: terraform plan"
echo "5. Run: terraform apply"
echo ""
