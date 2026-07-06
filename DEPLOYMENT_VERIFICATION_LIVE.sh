#!/bin/bash
# DEPLOYMENT VERIFICATION SCRIPT
# Run this after the GitHub Actions workflow completes
# This script verifies all infrastructure is deployed and system is working

set -e

echo "================================"
echo "DEPLOYMENT VERIFICATION SCRIPT"
echo "================================"
echo ""

# Configuration
AWS_REGION="us-east-1"
PROJECT_NAME="algo"
ENVIRONMENT="dev"

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "Step 1: Verify AWS Infrastructure Created"
echo "=========================================="
echo ""

# Check RDS database
echo "Checking RDS database..."
DB_STATUS=$(aws rds describe-db-instances \
  --db-instance-identifier "${PROJECT_NAME}-db" \
  --region "$AWS_REGION" \
  --query 'DBInstances[0].DBInstanceStatus' \
  --output text 2>/dev/null || echo "NOT_FOUND")

if [ "$DB_STATUS" = "available" ]; then
  echo -e "${GREEN}✓ RDS database is available${NC}"
  RDS_ENDPOINT=$(aws rds describe-db-instances \
    --db-instance-identifier "${PROJECT_NAME}-db" \
    --region "$AWS_REGION" \
    --query 'DBInstances[0].Endpoint.Address' \
    --output text)
  echo "  Endpoint: $RDS_ENDPOINT"
else
  echo -e "${RED}✗ RDS database NOT available (status: $DB_STATUS)${NC}"
  exit 1
fi

# Check Lambda Orchestrator
echo ""
echo "Checking Lambda Orchestrator..."
ORCHESTRATOR_LAMBDA=$(aws lambda get-function \
  --function-name "${PROJECT_NAME}-orchestrator-${ENVIRONMENT}" \
  --region "$AWS_REGION" \
  --query 'Configuration.FunctionName' \
  --output text 2>/dev/null || echo "NOT_FOUND")

if [ "$ORCHESTRATOR_LAMBDA" != "NOT_FOUND" ]; then
  echo -e "${GREEN}✓ Orchestrator Lambda deployed${NC}"
  echo "  Function: $ORCHESTRATOR_LAMBDA"
else
  echo -e "${RED}✗ Orchestrator Lambda NOT found${NC}"
  exit 1
fi

# Check Lambda API
echo ""
echo "Checking Lambda API..."
API_LAMBDA=$(aws lambda get-function \
  --function-name "${PROJECT_NAME}-api-${ENVIRONMENT}" \
  --region "$AWS_REGION" \
  --query 'Configuration.FunctionName' \
  --output text 2>/dev/null || echo "NOT_FOUND")

if [ "$API_LAMBDA" != "NOT_FOUND" ]; then
  echo -e "${GREEN}✓ API Lambda deployed${NC}"
  echo "  Function: $API_LAMBDA"
else
  echo -e "${RED}✗ API Lambda NOT found${NC}"
  exit 1
fi

# Check EventBridge Rules
echo ""
echo "Checking EventBridge scheduling..."
RULES_COUNT=$(aws events list-rules \
  --region "$AWS_REGION" \
  --name-prefix "${PROJECT_NAME}-algo-schedule-" \
  --query 'Rules | length(@)' \
  --output text 2>/dev/null || echo "0")

if [ "$RULES_COUNT" -gt 0 ]; then
  echo -e "${GREEN}✓ EventBridge scheduling rules created${NC}"
  echo "  Rules count: $RULES_COUNT"
else
  echo -e "${RED}✗ EventBridge rules NOT found${NC}"
  exit 1
fi

echo ""
echo "Step 2: Verify Database Schema and Data"
echo "========================================"
echo ""

# Test database connection
echo "Testing database connection..."
DB_HOST=$(aws rds describe-db-instances \
  --db-instance-identifier "${PROJECT_NAME}-db" \
  --region "$AWS_REGION" \
  --query 'DBInstances[0].Endpoint.Address' \
  --output text)

# Get credentials from Secrets Manager
DB_USER=$(aws secretsmanager get-secret-value \
  --secret-id "${PROJECT_NAME}-db-credentials-${ENVIRONMENT}" \
  --region "$AWS_REGION" \
  --query 'SecretString' \
  --output text 2>/dev/null | jq -r '.username' || echo "postgres")

DB_PASSWORD=$(aws secretsmanager get-secret-value \
  --secret-id "${PROJECT_NAME}-db-credentials-${ENVIRONMENT}" \
  --region "$AWS_REGION" \
  --query 'SecretString' \
  --output text 2>/dev/null | jq -r '.password' || echo "")

# Try to connect (may fail if credentials not set up properly in this session)
if PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -U "$DB_USER" -d "${PROJECT_NAME}_${ENVIRONMENT}" -c "SELECT 1" 2>/dev/null; then
  echo -e "${GREEN}✓ Database connection successful${NC}"

  # Check stock_scores table
  SCORES_COUNT=$(PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -U "$DB_USER" -d "${PROJECT_NAME}_${ENVIRONMENT}" \
    -c "SELECT COUNT(*) FROM stock_scores WHERE composite_score > 0;" 2>/dev/null | tail -1 | xargs || echo "0")

  if [ "$SCORES_COUNT" -gt 100 ]; then
    echo -e "${GREEN}✓ Stock scores populated in database${NC}"
    echo "  Records: $SCORES_COUNT"
  else
    echo -e "${YELLOW}⚠ Stock scores table exists but has < 100 records (expected after loaders run)${NC}"
    echo "  Records: $SCORES_COUNT"
  fi

  # Check orchestrator_execution_log
  EXECUTIONS=$(PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -U "$DB_USER" -d "${PROJECT_NAME}_${ENVIRONMENT}" \
    -c "SELECT COUNT(*) FROM orchestrator_execution_log WHERE run_date >= CURRENT_DATE;" 2>/dev/null | tail -1 | xargs || echo "0")

  if [ "$EXECUTIONS" -gt 0 ]; then
    echo -e "${GREEN}✓ Orchestrator has executed${NC}"
    echo "  Executions today: $EXECUTIONS"
  else
    echo -e "${YELLOW}⚠ Orchestrator has not executed yet (will run on schedule)${NC}"
  fi

  # Check trades
  TRADES=$(PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -U "$DB_USER" -d "${PROJECT_NAME}_${ENVIRONMENT}" \
    -c "SELECT COUNT(*) FROM algo_trades WHERE entry_date >= CURRENT_DATE;" 2>/dev/null | tail -1 | xargs || echo "0")

  if [ "$TRADES" -gt 0 ]; then
    echo -e "${GREEN}✓ Trades have been executed${NC}"
    echo "  Trades today: $TRADES"
  else
    echo -e "${YELLOW}⚠ No trades yet (will execute when signals generated)${NC}"
  fi
else
  echo -e "${YELLOW}⚠ Could not connect to database (credentials may not be set in environment)${NC}"
fi

echo ""
echo "Step 3: Verify API Responses"
echo "============================"
echo ""

# Get API Gateway endpoint
API_ENDPOINT=$(aws apigateway get-rest-apis \
  --region "$AWS_REGION" \
  --query "items[?name=='${PROJECT_NAME}-api'].id" \
  --output text 2>/dev/null)

if [ -n "$API_ENDPOINT" ] && [ "$API_ENDPOINT" != "None" ]; then
  FULL_API_URL="https://${API_ENDPOINT}.execute-api.${AWS_REGION}.amazonaws.com/${ENVIRONMENT}"
  echo "API Gateway endpoint: $FULL_API_URL"

  # Test scores endpoint
  echo ""
  echo "Testing /api/algo/scores endpoint..."
  SCORES_RESPONSE=$(curl -s "${FULL_API_URL}/api/algo/scores?limit=5" | jq '.data.top | length' 2>/dev/null || echo "0")

  if [ "$SCORES_RESPONSE" -gt 0 ]; then
    echo -e "${GREEN}✓ /api/algo/scores returning data${NC}"
    echo "  Items returned: $SCORES_RESPONSE"
  else
    echo -e "${YELLOW}⚠ /api/algo/scores endpoint not responding with data yet${NC}"
  fi
else
  echo -e "${YELLOW}⚠ API Gateway not found or not yet deployed${NC}"
fi

echo ""
echo "================================"
echo "VERIFICATION COMPLETE"
echo "================================"
echo ""
echo "If all checks passed:"
echo "  ✓ Infrastructure deployed successfully"
echo "  ✓ System is operational"
echo "  ✓ Trades will execute on schedule"
echo ""
echo "Next steps:"
echo "  1. Wait for data loaders to run (2:15 AM ET)"
echo "  2. Orchestrator will execute at 9:30 AM ET"
echo "  3. Trades will appear in dashboard"
echo "  4. Growth scores will display in dashboard"
echo ""
