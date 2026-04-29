#!/bin/bash
#
# Batch 5 Verification Script
# Checks that all fixes are in place and the system is ready
#

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

check_result() {
  if [ $? -eq 0 ]; then
    echo -e "${GREEN}✓ PASS${NC}: $1"
  else
    echo -e "${RED}✗ FAIL${NC}: $1"
  fi
}

echo "========================================"
echo "   BATCH 5 VERIFICATION REPORT"
echo "========================================"
echo ""

echo "1. PYTHON SYNTAX CHECK"
echo "   Compiling all 52 loaders..."
python3 -m py_compile load*.py 2>&1 | grep -i error && {
  echo -e "${RED}✗ Syntax errors found${NC}"
  exit 1
} || {
  echo -e "${GREEN}✓ All 52 loaders compile${NC}"
}
echo ""

echo "2. CRITICAL FIXES VERIFICATION"
echo ""
echo "   A. Column name fix (operating_expenses):"
grep -q "operating_expenses.*EXCLUDED.operating_expenses" loadquarterlyincomestatement.py
check_result "operating_expenses column in ON CONFLICT clause"
echo ""

echo "   B. Docstring fixes:"
for file in quarterlyincomestatement annualincomestatement annualbalancesheet dailycompanydata; do
  grep -q '#!/usr/bin/env python3' "load${file}.py"
  check_result "load${file}.py has proper shebang"
done
echo ""

echo "   C. Connection retry logic:"
for file in annualbalancesheet annualincomestatement quarterlyincomestatement; do
  grep -q "max_retries = 3" "load${file}.py"
  check_result "load${file}.py has connection retry logic"
done
echo ""

echo "3. INFRASTRUCTURE READINESS"
echo ""
for template in template-app-ecs-tasks.yml template-app-stocks.yml template-core.yml; do
  [ -f "$template" ] && echo -e "${GREEN}✓${NC} $template found" || echo -e "${RED}✗${NC} $template missing"
done
echo ""

echo "4. DOCKERFILES"
DOCKERFILE_COUNT=$(ls -1 Dockerfile.load* 2>/dev/null | wc -l)
echo "   Found $DOCKERFILE_COUNT Dockerfiles"
if [ $DOCKERFILE_COUNT -ge 20 ]; then
  echo -e "${GREEN}✓ Sufficient Dockerfiles for loaders${NC}"
else
  echo -e "${YELLOW}⚠ Only $DOCKERFILE_COUNT Dockerfiles (expected 20+)${NC}"
fi
echo ""

echo "5. GIT REPOSITORY STATUS"
echo ""
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
echo "   Current branch: $CURRENT_BRANCH"
if [ "$CURRENT_BRANCH" = "main" ]; then
  echo -e "${GREEN}✓ On main branch${NC}"
else
  echo -e "${YELLOW}⚠ Not on main branch${NC}"
fi
echo ""

LATEST=$(git log -1 --oneline)
echo "   Latest commit: $LATEST"
echo ""

echo "6. RECENT COMMITS WITH TRIGGER PATTERNS"
echo ""
git log --oneline -10 | head -5 | while read hash msg; do
  if echo "$msg" | grep -qi -E "fix|trigger|column|retry"; then
    echo -e "   ${GREEN}✓${NC} $hash $msg"
  fi
done
echo ""

echo "7. PYTHON ENVIRONMENT"
echo ""
python3 --version | sed 's/^/   /'
echo ""
echo "   Required packages:"
for pkg in psycopg2 yfinance pandas boto3 requests; do
  python3 -c "import ${pkg}" 2>/dev/null && echo -e "   ${GREEN}✓${NC} $pkg" || echo -e "   ${RED}✗${NC} $pkg"
done
echo ""

echo "8. AWS CREDENTIALS"
echo ""
if [ -n "$AWS_ACCESS_KEY_ID" ]; then
  echo -e "   ${GREEN}✓ AWS credentials loaded${NC}"
else
  echo -e "   ${YELLOW}⚠ AWS credentials not set${NC}"
fi
echo ""

if [ -n "$DB_HOST" ]; then
  echo -e "   ${GREEN}✓ Database config loaded (DB_HOST=$DB_HOST)${NC}"
else
  echo -e "   ${YELLOW}⚠ Database config not set (will default to localhost)${NC}"
fi
echo ""

echo "========================================"
echo "   NEXT STEPS"
echo "========================================"
echo ""
echo "1. GitHub Actions Workflow:"
echo "   Visit: https://github.com/argie33/algo/actions"
echo "   Look for: 'Data Loaders Pipeline'"
echo "   Should have been triggered by recent commits"
echo ""
echo "2. Monitor ECS Task Execution:"
echo "   Use AWS Console → ECS → stocks-cluster"
echo "   Or: aws ecs list-tasks --cluster stocks-cluster --region us-east-1"
echo ""
echo "3. Check CloudWatch Logs:"
echo "   Log group prefix: /ecs/load-"
echo "   Or: aws logs tail /ecs/load-quarterlyincomestatement --follow"
echo ""
echo "4. Verify Data Loaded:"
echo "   Connect to RDS and run:"
echo "   SELECT COUNT(*) FROM quarterly_income_statement;"
echo ""
echo "========================================"
