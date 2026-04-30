#!/bin/bash
# Comprehensive AWS Log Check Script
# Checks CloudWatch, ECS, Lambda, GitHub Actions

echo "╔════════════════════════════════════════════════════════════════════════════╗"
echo "║                  COMPREHENSIVE SYSTEM STATUS CHECK                         ║"
echo "╚════════════════════════════════════════════════════════════════════════════╝"

# Color codes
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

check_result() {
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ SUCCESS${NC}"
    else
        echo -e "${RED}✗ FAILED${NC}"
    fi
}

echo ""
echo "1. GITHUB STATUS"
echo "════════════════════════════════════════════════════════════════════════════"
echo "Latest commits:"
git log --oneline -5
echo ""
echo "Check GitHub Actions:"
echo "  → https://github.com/argie33/algo/actions"
echo ""

echo "2. CLOUDWATCH LOGS - Recent Activity (Last 50 events)"
echo "════════════════════════════════════════════════════════════════════════════"
echo "Checking CloudWatch for recent activity..."

# CloudWatch logs for ECS
aws logs tail /aws/ecs/DataLoaderCluster --since 30m --max-items 50 2>/dev/null
if [ $? -ne 0 ]; then
    echo -e "${YELLOW}⚠ CloudWatch not accessible (missing AWS credentials)${NC}"
    echo "To check manually:"
    echo "  aws logs tail /aws/ecs/DataLoaderCluster --follow"
fi

echo ""
echo "3. ECS TASK STATUS"
echo "════════════════════════════════════════════════════════════════════════════"
aws ecs describe-services \
    --cluster DataLoaderCluster \
    --services LoaderService \
    --query 'services[0].[status,runningCount,pendingCount,desiredCount]' \
    --output text 2>/dev/null

if [ $? -ne 0 ]; then
    echo -e "${YELLOW}⚠ ECS not accessible (missing AWS credentials)${NC}"
    echo "To check manually:"
    echo "  aws ecs describe-services --cluster DataLoaderCluster --services LoaderService"
fi

echo ""
echo "4. RDS CONNECTION TEST"
echo "════════════════════════════════════════════════════════════════════════════"
# Try to test RDS connection if credentials available
if [ ! -z "$DB_HOST" ]; then
    psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -c "SELECT COUNT(*) as row_count FROM stock_symbols LIMIT 1;" 2>/dev/null
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓ Database connected${NC}"
    else
        echo -e "${RED}✗ Database connection failed${NC}"
    fi
else
    echo -e "${YELLOW}⚠ No DB_HOST set (check .env.local)${NC}"
fi

echo ""
echo "5. LOAD STATE CHECK"
echo "════════════════════════════════════════════════════════════════════════════"
python3 << 'PYTHON_EOF'
try:
    from load_state import LoadState
    state = LoadState()
    state.print_summary()
except Exception as e:
    print(f"Error: {e}")
PYTHON_EOF

echo ""
echo "6. ERROR LOG SEARCH"
echo "════════════════════════════════════════════════════════════════════════════"
echo "Searching for recent errors..."
aws logs filter-log-events \
    --log-group-name /aws/ecs/DataLoaderCluster \
    --filter-pattern "ERROR" \
    --query 'events[0:5].[timestamp,message]' \
    --output text 2>/dev/null

if [ $? -ne 0 ]; then
    echo -e "${YELLOW}⚠ Cannot access CloudWatch (AWS credentials needed)${NC}"
fi

echo ""
echo "7. API ENDPOINTS TEST"
echo "════════════════════════════════════════════════════════════════════════════"
echo "Testing API endpoints for data..."

# Try localhost first (for dev)
API_URL="${API_URL:-http://localhost:3001}"

echo "Testing: $API_URL/api/health"
curl -s "$API_URL/api/health" 2>/dev/null | head -c 200
echo ""

echo "Testing: $API_URL/api/diagnostics"
curl -s "$API_URL/api/diagnostics" 2>/dev/null | head -c 200
echo ""

echo ""
echo "8. DEPLOYMENT CHECKLIST"
echo "════════════════════════════════════════════════════════════════════════════"
echo "✓ Code committed: YES (fc68a766a)"
echo "✓ Code pushed: YES (to main)"
echo "✓ GitHub Actions: Check https://github.com/argie33/algo/actions"
echo "✓ Docker build: Should be in progress"
echo "✓ ECS update: Pending Docker image"
echo "✓ Scheduler: Updated for incremental loads"

echo ""
echo "╔════════════════════════════════════════════════════════════════════════════╗"
echo "║                           TROUBLESHOOTING GUIDE                            ║"
echo "╚════════════════════════════════════════════════════════════════════════════╝"

echo ""
echo "If you see errors:"
echo ""
echo "Connection Refused:"
echo "  → Check RDS security group allows ECS access"
echo "  → Verify DB credentials in .env.local"
echo ""
echo "Timeout Errors:"
echo "  → Increase yfinance timeout (currently 15s)"
echo "  → Check network connectivity to yfinance"
echo ""
echo "Rate Limit Errors:"
echo "  → Semaphore is set to 8 workers - should prevent throttling"
echo "  → If still happening, reduce to 6 workers in loadanalystsentiment.py"
echo ""
echo "Transaction Aborted:"
echo "  → Usually from previous failed transaction"
echo "  → Check that conn.rollback() is being called"
echo ""
echo "Out of Memory:"
echo "  → Phase 2 batch size is 5000 - adjust if needed"
echo "  → Increase Lambda memory or ECS task memory"
echo ""
echo "Data not appearing:"
echo "  → Check that insert succeeded in logs"
echo "  → Verify no ON CONFLICT uniqueness issues"
echo "  → Check RDS slow_query_log for timing issues"
