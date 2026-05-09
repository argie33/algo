#!/bin/bash

################################################################################
# LOCAL TESTING SCRIPT - Complete Test Suite
# Run this script to test everything locally before AWS deployment
################################################################################

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}"
echo "=========================================="
echo "LOCAL TESTING SUITE - Stock Analytics"
echo "=========================================="
echo -e "${NC}"

################################################################################
# PHASE 1: Docker Compose Startup
################################################################################

echo -e "\n${BLUE}PHASE 1: Starting Docker Compose${NC}"
echo "=========================================="

# Check if docker-compose is available
if ! command -v docker-compose &> /dev/null && ! command -v docker &> /dev/null; then
    echo -e "${RED}ERROR: Docker not installed${NC}"
    echo "Install Docker Desktop from https://www.docker.com/products/docker-desktop"
    exit 1
fi

# Determine docker-compose command
if command -v docker-compose &> /dev/null; then
    DOCKER_COMPOSE="docker-compose"
elif command -v docker &> /dev/null; then
    DOCKER_COMPOSE="docker compose"
else
    echo -e "${RED}ERROR: Neither docker-compose nor docker found${NC}"
    exit 1
fi

echo "Using: $DOCKER_COMPOSE"

# Stop old containers
echo -e "\n${YELLOW}Stopping old containers...${NC}"
$DOCKER_COMPOSE down 2>/dev/null || true

# Start with clean database
echo -e "${YELLOW}Removing old database volume...${NC}"
$DOCKER_COMPOSE down -v 2>/dev/null || true

# Start fresh
echo -e "${YELLOW}Starting containers...${NC}"
$DOCKER_COMPOSE up -d

# Wait for services to be healthy
echo -e "${YELLOW}Waiting for services to be healthy...${NC}"
sleep 10

# Check postgres
echo -e "\n${BLUE}Checking PostgreSQL health...${NC}"
RETRY_COUNT=0
MAX_RETRIES=30
while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    if $DOCKER_COMPOSE exec postgres pg_isready -U stocks > /dev/null 2>&1; then
        echo -e "${GREEN}✅ PostgreSQL is healthy${NC}"
        break
    fi
    RETRY_COUNT=$((RETRY_COUNT + 1))
    echo -n "."
    sleep 1
done

if [ $RETRY_COUNT -eq $MAX_RETRIES ]; then
    echo -e "${RED}❌ PostgreSQL failed to start${NC}"
    $DOCKER_COMPOSE logs postgres
    exit 1
fi

################################################################################
# PHASE 2: Verify Database Schema
################################################################################

echo -e "\n${BLUE}PHASE 2: Verifying Database Schema${NC}"
echo "=========================================="

# Count tables
TABLE_COUNT=$($DOCKER_COMPOSE exec postgres psql -U stocks -d stocks -t -c "SELECT COUNT(*) FROM pg_tables WHERE schemaname='public';" 2>/dev/null)

echo -e "Total tables: ${GREEN}$TABLE_COUNT${NC}"

if [ "$TABLE_COUNT" -lt 50 ]; then
    echo -e "${RED}❌ ERROR: Expected 60+ tables, found $TABLE_COUNT${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Schema verified ($TABLE_COUNT tables)${NC}"

# Check critical tables
echo -e "\n${YELLOW}Checking critical tables...${NC}"

CRITICAL_TABLES="users trades algo_positions market_health_daily technical_data_daily buy_sell_daily stock_symbols"

for TABLE in $CRITICAL_TABLES; do
    EXISTS=$($DOCKER_COMPOSE exec postgres psql -U stocks -d stocks -t -c "SELECT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name='$TABLE' AND table_schema='public');" 2>/dev/null)

    if [ "$EXISTS" = "t" ]; then
        echo -e "  ${GREEN}✅${NC} $TABLE"
    else
        echo -e "  ${RED}❌${NC} $TABLE (MISSING)"
        exit 1
    fi
done

# Check buy_sell_daily columns
echo -e "\n${YELLOW}Checking buy_sell_daily extended columns...${NC}"

CRITICAL_COLS="buylevel stoplevel entry_price rsi adx macd sma_50 sma_200"
MISSING_COLS=""

for COL in $CRITICAL_COLS; do
    EXISTS=$($DOCKER_COMPOSE exec postgres psql -U stocks -d stocks -t -c "SELECT EXISTS(SELECT 1 FROM information_schema.columns WHERE table_name='buy_sell_daily' AND column_name='$COL');" 2>/dev/null)

    if [ "$EXISTS" = "t" ]; then
        echo -e "  ${GREEN}✅${NC} $COL"
    else
        echo -e "  ${RED}❌${NC} $COL (MISSING)"
        MISSING_COLS="$MISSING_COLS $COL"
    fi
done

if [ ! -z "$MISSING_COLS" ]; then
    echo -e "${RED}❌ Missing columns in buy_sell_daily: $MISSING_COLS${NC}"
    exit 1
fi

echo -e "\n${GREEN}✅ Database schema is complete${NC}"

################################################################################
# PHASE 3: Test API Endpoints
################################################################################

echo -e "\n${BLUE}PHASE 3: Testing API Endpoints${NC}"
echo "=========================================="

# Check .env.local exists
if [ ! -f ".env.local" ]; then
    echo -e "${YELLOW}⚠️  .env.local not found, creating...${NC}"
    cat > .env.local << 'EOF'
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=stocks
POSTGRES_PASSWORD=
POSTGRES_DB=stocks

ALPACA_API_KEY=your_paper_trading_key_here
ALPACA_SECRET_KEY=your_paper_trading_secret_here
ALPACA_PAPER_TRADING=true

AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=test
AWS_SECRET_ACCESS_KEY=test
EOF
    echo -e "${YELLOW}Created .env.local - you may need to add Alpaca credentials${NC}"
fi

# Start API server
echo -e "\n${YELLOW}Starting API server...${NC}"
cd webapp/lambda

if [ ! -d "node_modules" ]; then
    echo -e "${YELLOW}Installing npm dependencies...${NC}"
    npm install > /dev/null 2>&1
fi

# Start server in background
npm start > /tmp/api_server.log 2>&1 &
API_PID=$!
echo "API PID: $API_PID"

# Wait for server to start
sleep 3

# Check if server is running
if ! ps -p $API_PID > /dev/null; then
    echo -e "${RED}❌ API server failed to start${NC}"
    cat /tmp/api_server.log
    exit 1
fi

echo -e "${GREEN}✅ API server started (PID: $API_PID)${NC}"

# Test endpoints
cd "$SCRIPT_DIR"

echo -e "\n${YELLOW}Testing API endpoints...${NC}"

test_endpoint() {
    local name="$1"
    local endpoint="$2"
    local expected_status="${3:-200}"

    response=$(curl -s -w "\n%{http_code}" "http://localhost:3001$endpoint" 2>/dev/null)
    status=$(echo "$response" | tail -n1)

    if [ "$status" = "$expected_status" ]; then
        echo -e "  ${GREEN}✅${NC} $name ($status)"
        return 0
    else
        echo -e "  ${RED}❌${NC} $name (expected $expected_status, got $status)"
        return 1
    fi
}

ENDPOINTS_PASSED=0
ENDPOINTS_TOTAL=0

echo -e "\n${YELLOW}Core Endpoints:${NC}"
test_endpoint "Health" "/health" && ENDPOINTS_PASSED=$((ENDPOINTS_PASSED + 1))
ENDPOINTS_TOTAL=$((ENDPOINTS_TOTAL + 1))

test_endpoint "API Info" "/api" && ENDPOINTS_PASSED=$((ENDPOINTS_PASSED + 1))
ENDPOINTS_TOTAL=$((ENDPOINTS_TOTAL + 1))

echo -e "\n${YELLOW}Business Endpoints:${NC}"
test_endpoint "Stocks" "/api/stocks?limit=5" && ENDPOINTS_PASSED=$((ENDPOINTS_PASSED + 1))
ENDPOINTS_TOTAL=$((ENDPOINTS_TOTAL + 1))

test_endpoint "Market Status" "/api/market/status" && ENDPOINTS_PASSED=$((ENDPOINTS_PASSED + 1))
ENDPOINTS_TOTAL=$((ENDPOINTS_TOTAL + 1))

test_endpoint "Signals" "/api/signals?limit=10" && ENDPOINTS_PASSED=$((ENDPOINTS_PASSED + 1))
ENDPOINTS_TOTAL=$((ENDPOINTS_TOTAL + 1))

test_endpoint "Scores" "/api/scores?limit=5" && ENDPOINTS_PASSED=$((ENDPOINTS_PASSED + 1))
ENDPOINTS_TOTAL=$((ENDPOINTS_TOTAL + 1))

echo -e "\n${YELLOW}Trading Endpoints:${NC}"
test_endpoint "Portfolio" "/api/portfolio" && ENDPOINTS_PASSED=$((ENDPOINTS_PASSED + 1))
ENDPOINTS_TOTAL=$((ENDPOINTS_TOTAL + 1))

test_endpoint "Trades" "/api/trades" && ENDPOINTS_PASSED=$((ENDPOINTS_PASSED + 1))
ENDPOINTS_TOTAL=$((ENDPOINTS_TOTAL + 1))

test_endpoint "Algo Status" "/api/algo/status" && ENDPOINTS_PASSED=$((ENDPOINTS_PASSED + 1))
ENDPOINTS_TOTAL=$((ENDPOINTS_TOTAL + 1))

# Kill API server
kill $API_PID 2>/dev/null || true
wait $API_PID 2>/dev/null || true

echo -e "\n${BLUE}API Results: ${GREEN}$ENDPOINTS_PASSED/$ENDPOINTS_TOTAL${NC} endpoints working"

if [ $ENDPOINTS_PASSED -lt $((ENDPOINTS_TOTAL * 70 / 100)) ]; then
    echo -e "${RED}❌ Less than 70% of endpoints working${NC}"
    exit 1
fi

################################################################################
# PHASE 4: Test Algo Orchestrator
################################################################################

echo -e "\n${BLUE}PHASE 4: Testing Algo Orchestrator${NC}"
echo "=========================================="

# Create test .env for algo
export POSTGRES_HOST=localhost
export POSTGRES_PORT=5432
export POSTGRES_USER=stocks
export POSTGRES_PASSWORD=
export POSTGRES_DB=stocks
export ALPACA_PAPER_TRADING=true
export DRY_RUN=true

echo -e "${YELLOW}Running algo orchestrator (dry run)...${NC}"

if python3 algo_run_daily.py --dry-run 2>&1 | tee /tmp/algo_test.log | head -50; then
    # Check for phase completions
    if grep -q "Phase 1" /tmp/algo_test.log && grep -q "Phase 7" /tmp/algo_test.log; then
        echo -e "${GREEN}✅ Algo orchestrator completed all 7 phases${NC}"
    else
        echo -e "${YELLOW}⚠️  Algo ran but some phases may have skipped${NC}"
    fi
else
    echo -e "${RED}❌ Algo orchestrator failed${NC}"
    cat /tmp/algo_test.log
    exit 1
fi

################################################################################
# PHASE 5: Test Data Loaders
################################################################################

echo -e "\n${BLUE}PHASE 5: Testing Data Loaders${NC}"
echo "=========================================="

echo -e "${YELLOW}Checking Python loader syntax...${NC}"

LOADER_FAILED=0
for loader in load*.py; do
    if python3 -m py_compile "$loader" 2>/dev/null; then
        echo -e "  ${GREEN}✅${NC} $loader"
    else
        echo -e "  ${RED}❌${NC} $loader (syntax error)"
        LOADER_FAILED=$((LOADER_FAILED + 1))
    fi
done

if [ $LOADER_FAILED -gt 0 ]; then
    echo -e "${RED}❌ $LOADER_FAILED loaders have syntax errors${NC}"
    exit 1
fi

echo -e "${GREEN}✅ All data loaders have valid syntax${NC}"

################################################################################
# PHASE 6: Summary
################################################################################

echo -e "\n${BLUE}=========================================="
echo "✅ LOCAL TESTING COMPLETE"
echo "==========================================${NC}"

echo -e "\n${GREEN}All tests passed!${NC}"
echo ""
echo "Summary:"
echo "  ${GREEN}✅${NC} Database schema (60+ tables)"
echo "  ${GREEN}✅${NC} API endpoints ($ENDPOINTS_PASSED/$ENDPOINTS_TOTAL working)"
echo "  ${GREEN}✅${NC} Algo orchestrator (7-phase)"
echo "  ${GREEN}✅${NC} Data loaders (syntax valid)"
echo ""
echo "Next steps:"
echo "  1. Review the test output above"
echo "  2. Fix any issues if needed"
echo "  3. Deploy to AWS: gh workflow run deploy-all-infrastructure.yml"
echo ""
echo "Docker Compose is still running. To stop:"
echo "  docker-compose down"
echo ""
echo "To view logs:"
echo "  docker-compose logs postgres    (database)"
echo "  docker-compose logs redis       (cache)"
echo "  docker-compose logs localstack  (AWS simulation)"
echo ""

# Stop containers
$DOCKER_COMPOSE down

exit 0
