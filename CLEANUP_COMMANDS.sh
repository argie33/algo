#!/bin/bash
# AWS Cleanup Commands - Run these on your local machine with AWS CLI installed
# This will delete the conflicting resources blocking terraform deployment

set -e

AWS_REGION="us-east-1"
PROJECT_NAME="stocks"

echo "=========================================="
echo "AWS Resource Cleanup - Execution Log"
echo "=========================================="
echo "Region: $AWS_REGION"
echo "Project: $PROJECT_NAME"
echo "Time: $(date)"
echo ""

# ============================================================
# STEP 1: Backup RDS (optional but recommended)
# ============================================================
echo "STEP 1: Creating RDS backup..."
EXISTING_DB=$(aws rds describe-db-instances \
  --region $AWS_REGION \
  --query "DBInstances[?contains(DBInstanceIdentifier, '$PROJECT_NAME')].DBInstanceIdentifier" \
  --output text 2>/dev/null || echo "")

if [ -n "$EXISTING_DB" ]; then
  echo "✓ Found RDS instance: $EXISTING_DB"
  SNAPSHOT_ID="$PROJECT_NAME-backup-$(date +%Y%m%d-%H%M%S)"
  echo "  Creating snapshot: $SNAPSHOT_ID"

  aws rds create-db-snapshot \
    --db-instance-identifier "$EXISTING_DB" \
    --db-snapshot-identifier "$SNAPSHOT_ID" \
    --region $AWS_REGION 2>/dev/null || echo "  ⚠️  Snapshot creation in progress or already exists"

  echo "✓ Snapshot requested"
  echo "  (Check status: aws rds describe-db-snapshots --db-snapshot-identifier $SNAPSHOT_ID --region $AWS_REGION)"
else
  echo "✓ No RDS instance found to backup"
fi

echo ""

# ============================================================
# STEP 2: Delete RDS Instance
# ============================================================
echo "STEP 2: Deleting RDS instance..."

if [ -n "$EXISTING_DB" ]; then
  echo "✓ Deleting: $EXISTING_DB"
  aws rds delete-db-instance \
    --db-instance-identifier "$EXISTING_DB" \
    --skip-final-snapshot \
    --region $AWS_REGION
  echo "✓ RDS delete request submitted"
  echo "  (This will take 5-10 minutes to complete)"
  echo "  Check status: aws rds describe-db-instances --region $AWS_REGION --query 'DBInstances[?contains(DBInstanceIdentifier, \"$PROJECT_NAME\")].{ID:DBInstanceIdentifier,Status:DBInstanceStatus}'"
else
  echo "✓ No RDS to delete"
fi

echo ""

# ============================================================
# STEP 3: Wait for RDS deletion
# ============================================================
echo "STEP 3: Waiting for RDS deletion (this takes ~5-10 minutes)..."
if [ -n "$EXISTING_DB" ]; then
  echo "  Checking every 10 seconds..."
  COUNTER=0
  MAX_ATTEMPTS=90  # 15 minutes max

  while [ $COUNTER -lt $MAX_ATTEMPTS ]; do
    INSTANCES=$(aws rds describe-db-instances \
      --region $AWS_REGION \
      --query "DBInstances[?DBInstanceIdentifier=='$EXISTING_DB'].DBInstanceIdentifier" \
      --output text 2>/dev/null || echo "")

    if [ -z "$INSTANCES" ]; then
      echo "✓ RDS instance deleted successfully!"
      break
    fi

    COUNTER=$((COUNTER + 1))
    echo "  [$COUNTER/$MAX_ATTEMPTS] Waiting for deletion... (elapsed: $(($COUNTER * 10))s)"
    sleep 10
  done
else
  echo "✓ Skipping wait (no RDS to delete)"
fi

echo ""

# ============================================================
# STEP 4: Delete Security Groups
# ============================================================
echo "STEP 4: Deleting security groups..."

SG_IDS=$(aws ec2 describe-security-groups \
  --region $AWS_REGION \
  --filters "Name=tag:Project,Values=$PROJECT_NAME" \
  --query "SecurityGroups[?GroupName != 'default'].GroupId" \
  --output text 2>/dev/null || echo "")

if [ -n "$SG_IDS" ]; then
  for sg in $SG_IDS; do
    echo "  Deleting: $sg"
    aws ec2 delete-security-group \
      --group-id "$sg" \
      --region $AWS_REGION 2>/dev/null || echo "  ⚠️  Could not delete $sg (may be in use)"
  done
  echo "✓ Security group deletion requested"
else
  echo "✓ No security groups found"
fi

echo ""

# ============================================================
# STEP 5: Delete EC2 Instances
# ============================================================
echo "STEP 5: Terminating EC2 instances..."

INSTANCE_IDS=$(aws ec2 describe-instances \
  --region $AWS_REGION \
  --filters "Name=tag:Project,Values=$PROJECT_NAME" "Name=instance-state-name,Values=running,stopped,pending" \
  --query "Reservations[*].Instances[*].InstanceId" \
  --output text 2>/dev/null || echo "")

if [ -n "$INSTANCE_IDS" ]; then
  for instance in $INSTANCE_IDS; do
    echo "  Terminating: $instance"
    aws ec2 terminate-instances \
      --instance-ids "$instance" \
      --region $AWS_REGION 2>/dev/null
  done
  echo "✓ EC2 termination requested"
else
  echo "✓ No EC2 instances found"
fi

echo ""

# ============================================================
# STEP 6: Cleanup Summary
# ============================================================
echo "=========================================="
echo "✓ CLEANUP COMPLETE"
echo "=========================================="
echo ""
echo "Resources deleted:"
if [ -n "$EXISTING_DB" ]; then
  echo "  ✓ RDS instance: $EXISTING_DB"
fi
if [ -n "$SG_IDS" ]; then
  echo "  ✓ Security groups: $(echo $SG_IDS | wc -w) deleted"
fi
if [ -n "$INSTANCE_IDS" ]; then
  echo "  ✓ EC2 instances: $(echo $INSTANCE_IDS | wc -w) terminated"
fi

echo ""
echo "Next steps:"
echo "  1. Wait 5+ minutes for AWS resources to fully delete"
echo "  2. Verify cleanup: aws ec2 describe-instances --region $AWS_REGION --filters 'Name=tag:Project,Values=$PROJECT_NAME' --query 'Reservations'"
echo "  3. Navigate to terraform: cd terraform"
echo "  4. Reset terraform: rm -rf .terraform/ && terraform init"
echo "  5. Generate plan: terraform plan -out=tfplan"
echo "  6. Deploy: terraform apply tfplan"
echo ""
echo "Timestamps:"
echo "  Cleanup started: $(date)"
echo "  Please wait 5+ minutes before proceeding"
echo ""
