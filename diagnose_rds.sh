#!/bin/bash
# RDS Connectivity Diagnostic Script
# Usage: ./diagnose_rds.sh

set -e

echo "════════════════════════════════════════════════════════════════"
echo "RDS Connectivity Diagnostic"
echo "════════════════════════════════════════════════════════════════"

REGION="us-east-1"

# Extract project and environment from terraform.tfvars
PROJECT=$(grep '^project_name' terraform/terraform.tfvars | cut -d'"' -f2)
ENVIRONMENT=$(grep '^environment' terraform/terraform.tfvars | cut -d'"' -f2)

echo ""
echo "Configuration:"
echo "  Project: $PROJECT"
echo "  Environment: $ENVIRONMENT"
echo "  Region: $REGION"

# RDS Instance name
RDS_INSTANCE="${PROJECT}-db"

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "Step 1: Check RDS Instance Status"
echo "════════════════════════════════════════════════════════════════"

RDS_STATUS=$(aws rds describe-db-instances \
  --db-instance-identifier "$RDS_INSTANCE" \
  --region "$REGION" \
  --query 'DBInstances[0].DBInstanceStatus' \
  --output text 2>/dev/null || echo "NOT_FOUND")

if [ "$RDS_STATUS" = "NOT_FOUND" ]; then
  echo "❌ RDS Instance NOT FOUND: $RDS_INSTANCE"
  echo ""
  echo "Available RDS instances:"
  aws rds describe-db-instances \
    --region "$REGION" \
    --query 'DBInstances[].{ID:DBInstanceIdentifier,Status:DBInstanceStatus,Engine:Engine}' \
    --output table
  exit 1
fi

echo "✅ RDS Instance: $RDS_INSTANCE"
echo "   Status: $RDS_STATUS"

if [ "$RDS_STATUS" != "available" ]; then
  echo "⚠️  WARNING: Instance is not 'available' - it's in state: $RDS_STATUS"
  echo "   Please wait for instance to finish starting/modifying."
  exit 1
fi

# Get RDS details
RDS_ENDPOINT=$(aws rds describe-db-instances \
  --db-instance-identifier "$RDS_INSTANCE" \
  --region "$REGION" \
  --query 'DBInstances[0].Endpoint.Address' \
  --output text)

RDS_PORT=$(aws rds describe-db-instances \
  --db-instance-identifier "$RDS_INSTANCE" \
  --region "$REGION" \
  --query 'DBInstances[0].Endpoint.Port' \
  --output text)

RDS_DB_NAME=$(aws rds describe-db-instances \
  --db-instance-identifier "$RDS_INSTANCE" \
  --region "$REGION" \
  --query 'DBInstances[0].DBName' \
  --output text)

echo "   Endpoint: $RDS_ENDPOINT:$RDS_PORT"
echo "   Database: $RDS_DB_NAME"

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "Step 2: Check Secrets Manager Credentials"
echo "════════════════════════════════════════════════════════════════"

SECRET_ID="${PROJECT}-db-credentials-${ENVIRONMENT}"

echo "Secret ID: $SECRET_ID"

SECRET_VALUE=$(aws secretsmanager get-secret-value \
  --secret-id "$SECRET_ID" \
  --region "$REGION" \
  --query 'SecretString' \
  --output text 2>/dev/null || echo "")

if [ -z "$SECRET_VALUE" ]; then
  echo "❌ Secret NOT FOUND or cannot be accessed"
  exit 1
fi

echo "✅ Secret found"

# Parse secret (safely)
SECRET_HOST=$(echo "$SECRET_VALUE" | jq -r '.host // empty')
SECRET_PORT=$(echo "$SECRET_VALUE" | jq -r '.port // "5432"')
SECRET_USER=$(echo "$SECRET_VALUE" | jq -r '.username // empty')
SECRET_PASSWORD=$(echo "$SECRET_VALUE" | jq -r '.password // empty')
SECRET_DBNAME=$(echo "$SECRET_VALUE" | jq -r '.dbname // empty')

echo "   Host: $SECRET_HOST"
echo "   Port: $SECRET_PORT"
echo "   User: $SECRET_USER"
echo "   Database: $SECRET_DBNAME"

# Verify host matches RDS endpoint
if [ "$SECRET_HOST" != "$RDS_ENDPOINT" ]; then
  echo "⚠️  WARNING: Secret host doesn't match RDS endpoint!"
  echo "   Secret: $SECRET_HOST"
  echo "   RDS:    $RDS_ENDPOINT"
fi

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "Step 3: Check Lambda Environment Variables"
echo "════════════════════════════════════════════════════════════════"

API_LAMBDA="${PROJECT}-api-${ENVIRONMENT}"

echo "Lambda Function: $API_LAMBDA"

LAMBDA_CONFIG=$(aws lambda get-function-configuration \
  --function-name "$API_LAMBDA" \
  --region "$REGION" \
  --query 'Environment.Variables' \
  --output json 2>/dev/null || echo "{}")

if [ "$LAMBDA_CONFIG" = "{}" ]; then
  echo "❌ Could not retrieve Lambda configuration"
  exit 1
fi

echo "✅ Lambda Configuration:"
echo "$LAMBDA_CONFIG" | jq -r 'to_entries[] | "   \(.key): \(.value // "MISSING")"'

# Extract and verify DB_SECRET_ARN
DB_SECRET_ARN=$(echo "$LAMBDA_CONFIG" | jq -r '.DB_SECRET_ARN // empty')
DB_HOST_VAR=$(echo "$LAMBDA_CONFIG" | jq -r '.DB_HOST // empty')

if [ -z "$DB_SECRET_ARN" ]; then
  echo "⚠️  WARNING: DB_SECRET_ARN not set in Lambda"
fi

if [ -z "$DB_HOST_VAR" ]; then
  echo "⚠️  WARNING: DB_HOST not set in Lambda"
fi

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "Step 4: Verify VPC & Security Group Configuration"
echo "════════════════════════════════════════════════════════════════"

# Get Lambda VPC config
LAMBDA_VPC=$(aws lambda get-function-configuration \
  --function-name "$API_LAMBDA" \
  --region "$REGION" \
  --query 'VpcConfig.VpcId' \
  --output text 2>/dev/null || echo "")

LAMBDA_SG=$(aws lambda get-function-configuration \
  --function-name "$API_LAMBDA" \
  --region "$REGION" \
  --query 'VpcConfig.SecurityGroupIds[0]' \
  --output text 2>/dev/null || echo "")

echo "Lambda VPC: $LAMBDA_VPC"
echo "Lambda SG:  $LAMBDA_SG"

# Get RDS VPC and SG
RDS_VPC=$(aws rds describe-db-instances \
  --db-instance-identifier "$RDS_INSTANCE" \
  --region "$REGION" \
  --query 'DBInstances[0].DBSubnetGroup.VpcId' \
  --output text 2>/dev/null || echo "")

RDS_SG=$(aws rds describe-db-instances \
  --db-instance-identifier "$RDS_INSTANCE" \
  --region "$REGION" \
  --query 'DBInstances[0].VpcSecurityGroups[0].VpcSecurityGroupId' \
  --output text 2>/dev/null || echo "")

echo "RDS VPC:   $RDS_VPC"
echo "RDS SG:    $RDS_SG"

# Check if VPCs match
if [ "$LAMBDA_VPC" != "$RDS_VPC" ]; then
  echo "❌ ERROR: Lambda and RDS are in different VPCs!"
  echo "   Lambda: $LAMBDA_VPC"
  echo "   RDS:    $RDS_VPC"
  exit 1
fi

echo "✅ Lambda and RDS in same VPC"

# Check security group rules
echo ""
echo "Checking RDS Security Group Rules..."
INGRESS_RULES=$(aws ec2 describe-security-group-rules \
  --region "$REGION" \
  --filters "Name=group-id,Values=$RDS_SG" "Name=is-egress,Values=false" \
  --query 'SecurityGroupRules[].{Type:IpProtocol,Port:FromPort,Source:ReferencedGroupInfo.GroupId,CIDR:CidrIpv4}' \
  --output json 2>/dev/null || echo "[]")

echo "$INGRESS_RULES" | jq -r '.[] | "   Protocol: \(.Type), Port: \(.Port), Source: \(.Source // .CIDR // "UNKNOWN")"'

# Check if Lambda SG is allowed
if echo "$INGRESS_RULES" | jq -e ".[] | select(.Source == \"$LAMBDA_SG\" and (.Port == 5432 or .Port == -1))" > /dev/null 2>&1; then
  echo "✅ Lambda SG has access to RDS on port 5432"
else
  echo "⚠️  WARNING: Lambda SG may not have access to RDS port 5432"
  echo "   You may need to add an ingress rule to the RDS security group"
fi

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "Step 5: Test Database Connection (CloudShell equivalent)"
echo "════════════════════════════════════════════════════════════════"

echo "Note: Cannot test from local machine (would need to be in VPC)"
echo "To test from AWS CloudShell, run:"
echo ""
echo "  psql \\"
echo "    -h $SECRET_HOST \\"
echo "    -U $SECRET_USER \\"
echo "    -d $SECRET_DBNAME \\"
echo "    -c \"SELECT 1 as connection_test;\""
echo ""
echo "When prompted, enter password from Secrets Manager."

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "Step 6: Check Lambda CloudWatch Logs"
echo "════════════════════════════════════════════════════════════════"

LOG_GROUP="/aws/lambda/$API_LAMBDA"

echo "Log Group: $LOG_GROUP"

# Get latest logs
LATEST_LOGS=$(aws logs tail "$LOG_GROUP" \
  --region "$REGION" \
  --format short \
  --since 1h \
  2>/dev/null | tail -20 || echo "No logs found")

if [ -z "$LATEST_LOGS" ]; then
  echo "No recent logs found in CloudWatch"
else
  echo "Latest logs (last 20 lines, last 1 hour):"
  echo "$LATEST_LOGS"
fi

echo ""
echo "════════════════════════════════════════════════════════════════"
echo "Verification Results"
echo "════════════════════════════════════════════════════════════════"
echo "Review findings above for any ❌ or ⚠️ warnings."
echo "Fix any issues, then rerun this script to verify."
