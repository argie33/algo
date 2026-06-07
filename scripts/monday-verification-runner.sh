#!/bin/bash
# Monday Morning AWS Verification Script (June 9, 2026)
# Executes all 3 critical issue verifications via CloudWatch + RDS
# Run at 2:00 AM ET with: bash scripts/monday-verification-runner.sh

set -e

echo "============================================"
echo "MONDAY MORNING VERIFICATION (2026-06-09)"
echo "============================================"

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

LOG_GROUP="/aws/ecs/algo-loaders"
ORCHESTRATOR_LOG="/aws/lambda/algo-orchestrator"
AWS_REGION="us-east-1"

echo ""
echo "$(date '+%H:%M:%S UTC') — Starting verification suite"
echo ""

# ============================================================
# ISSUE #4: Verify Morning Prep Started at 2:00 AM ET
# ============================================================

echo -e "${YELLOW}[ISSUE #4]${NC} Verifying morning prep pipeline started at 2:00 AM ET..."

START_TIME=$(date -u -d "2 hours ago" '+%Y-%m-%dT%H:%M:%S')
aws logs filter-log-events \
  --log-group-name "$ORCHESTRATOR_LOG" \
  --start-time "$(date -d '06:00 UTC' +%s)000" \
  --filter-pattern "MORNING_PREP_VALIDATION" \
  --region "$AWS_REGION" \
  --query 'events[0:5].message' \
  --output text > /tmp/issue4_logs.txt 2>&1

if [ -s /tmp/issue4_logs.txt ]; then
  echo -e "${GREEN}✅ PASS${NC} — Orchestrator logs found"
  cat /tmp/issue4_logs.txt | head -3
else
  echo -e "${RED}❌ FAIL${NC} — No orchestrator logs found (may still be starting)"
fi

echo ""

# ============================================================
# ISSUE #2: Verify Loader Completion Detection
# ============================================================

echo -e "${YELLOW}[ISSUE #2]${NC} Verifying loader completion tracking..."

# Search for execution_completed timestamps in loader logs
aws logs filter-log-events \
  --log-group-name "$LOG_GROUP" \
  --start-time "$(date -d '02:00 ET' +%s)000" \
  --filter-pattern "execution_completed" \
  --region "$AWS_REGION" \
  --query 'events[*].{timestamp:@timestamp, message:message}' \
  --output text > /tmp/issue2_logs.txt 2>&1

LOADER_COUNT=$(wc -l < /tmp/issue2_logs.txt)

if [ "$LOADER_COUNT" -gt 0 ]; then
  echo -e "${GREEN}✅ PASS${NC} — Found $LOADER_COUNT loader completion records"
  cat /tmp/issue2_logs.txt | head -5
else
  echo -e "${YELLOW}⏳ PENDING${NC} — Loaders still executing (check again in 10 minutes)"
fi

echo ""

# ============================================================
# ISSUE #13: Verify Health Endpoint Freshness
# ============================================================

echo -e "${YELLOW}[ISSUE #13]${NC} Testing health endpoint freshness..."

HEALTH_RESPONSE=$(curl -s \
  -H "Origin: http://localhost:5173" \
  "https://d2u93283nn45h2.cloudfront.net/api/health")

SIGNAL_AGE=$(echo "$HEALTH_RESPONSE" | jq -r '.data.freshness.signal_age_hours // "ERROR"')
RDS_STATUS=$(echo "$HEALTH_RESPONSE" | jq -r '.data.rds_connection_pool.status // "ERROR"')

if [ "$SIGNAL_AGE" != "ERROR" ] && [ "$RDS_STATUS" = "HEALTHY" ]; then
  echo -e "${GREEN}✅ PASS${NC} — Health endpoint working"
  echo "  Signal age: $SIGNAL_AGE hours"
  echo "  RDS pool: $RDS_STATUS"
else
  echo -e "${RED}❌ FAIL${NC} — Health endpoint issue"
  echo "  Response: $HEALTH_RESPONSE"
fi

echo ""

# ============================================================
# DATABASE VERIFICATION (Requires AWS Credentials)
# ============================================================

echo -e "${YELLOW}[DATABASE CHECK]${NC} Verifying RDS loader status table..."

# Note: This requires RDS password from Secrets Manager or AWS Secrets
# Uncomment if you have credentials configured
# psql -h $RDS_ENDPOINT -U algo_admin -d algo_prod -c \
#   "SELECT table_name, status, completion_pct FROM data_loader_status
#    WHERE table_name IN ('company_data', 'stock_prices_daily', 'technical_data_daily')
#    ORDER BY last_updated DESC LIMIT 6;"

echo -e "${YELLOW}⚠️  NOTE${NC} — RDS query requires database credentials"
echo "   Run manually in AWS RDS Query Editor or psql"
echo ""

# ============================================================
# SUMMARY
# ============================================================

echo "============================================"
echo "VERIFICATION COMPLETE"
echo "============================================"
echo ""
echo "Next steps:"
echo "1. If all ✅ PASS — Issues verified working in production"
echo "2. If ⏳ PENDING — Wait 10 minutes, re-run script"
echo "3. If ❌ FAIL — Check CloudWatch logs for errors:"
echo "   - Log Group: /aws/ecs/algo-loaders"
echo "   - Log Group: /aws/lambda/algo-orchestrator"
echo ""
