#!/bin/bash
# Create missing CloudWatch log groups that CloudFormation expects
# This fixes UPDATE_FAILED errors when log groups were deleted

set -e

echo "🔧 Creating missing CloudWatch log groups..."

# List of log groups that CloudFormation expects but may be missing
LOG_GROUPS=(
  "/ecs/buysellmonthly-loader"
  "/ecs/buysellweekly-loader"
  "/ecs/companyprofile-loader"
)

RETENTION_DAYS=3

for log_group in "${LOG_GROUPS[@]}"; do
  echo "Checking $log_group..."

  # Check if log group exists
  if aws logs describe-log-groups --log-group-name-prefix "$log_group" --query "logGroups[?logGroupName=='$log_group']" --output text | grep -q "$log_group"; then
    echo "  ✅ Already exists"
  else
    echo "  📝 Creating..."
    aws logs create-log-group --log-group-name "$log_group" || true
    aws logs put-retention-policy --log-group-name "$log_group" --retention-in-days $RETENTION_DAYS || true
    echo "  ✅ Created with $RETENTION_DAYS day retention"
  fi
done

echo "✅ All required log groups verified/created"
