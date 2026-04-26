#!/bin/bash

# Color codes
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# API base URL
API_URL="http://localhost:3001"

echo "================================================"
echo "ENDPOINT VERIFICATION TEST SUITE"
echo "================================================"
echo ""

# Counter for results
TOTAL=0
PASSED=0
FAILED=0

# Test function
test_endpoint() {
    local method=$1
    local endpoint=$2
    local description=$3

    TOTAL=$((TOTAL + 1))

    echo -n "Testing $endpoint... "

    if [ "$method" == "GET" ]; then
        response=$(curl -s -o /dev/null -w "%{http_code}" "$API_URL$endpoint")
    else
        response=$(curl -s -X POST -H "Content-Type: application/json" \
            -d '{}' -o /dev/null -w "%{http_code}" "$API_URL$endpoint")
    fi

    if [ "$response" == "200" ] || [ "$response" == "201" ]; then
        echo -e "${GREEN}✅ OK ($response)${NC}"
        PASSED=$((PASSED + 1))
    else
        echo -e "${RED}❌ FAILED ($response)${NC}"
        FAILED=$((FAILED + 1))
    fi
}

echo "CORE SYSTEM ENDPOINTS"
echo "====================="
test_endpoint GET "/api/health" "Health check"
test_endpoint GET "/api/diagnostics" "Diagnostics"
test_endpoint GET "/api" "API info"
echo ""

echo "MARKET ENDPOINTS"
echo "================"
test_endpoint GET "/api/market/overview" "Market overview"
test_endpoint GET "/api/market/indices" "Market indices"
test_endpoint GET "/api/market/technicals" "Market technicals"
test_endpoint GET "/api/market/sentiment" "Market sentiment"
test_endpoint GET "/api/market/seasonality" "Market seasonality"
test_endpoint GET "/api/market/correlation" "Market correlation"
test_endpoint GET "/api/market/top-movers" "Market top movers"
test_endpoint GET "/api/market/cap-distribution" "Market cap distribution"
echo ""

echo "STOCKS ENDPOINTS"
echo "================"
test_endpoint GET "/api/stocks?limit=10" "List stocks (paginated)"
test_endpoint GET "/api/stocks/AAPL" "Get stock detail (AAPL)"
test_endpoint GET "/api/stocks/search?q=apple" "Search stocks"
test_endpoint GET "/api/stocks/deep-value" "Deep value stocks"
echo ""

echo "FINANCIALS ENDPOINTS"
echo "===================="
test_endpoint GET "/api/financials/AAPL/balance-sheet" "Balance sheet"
test_endpoint GET "/api/financials/AAPL/income-statement" "Income statement"
test_endpoint GET "/api/financials/AAPL/cash-flow" "Cash flow"
echo ""

echo "ECONOMIC ENDPOINTS"
echo "=================="
test_endpoint GET "/api/economic/leading-indicators" "Leading indicators"
test_endpoint GET "/api/economic/yield-curve-full" "Yield curve"
test_endpoint GET "/api/economic/calendar" "Economic calendar"
echo ""

echo "SIGNALS ENDPOINTS"
echo "================="
test_endpoint GET "/api/signals/daily" "Daily signals"
test_endpoint GET "/api/signals/weekly" "Weekly signals"
test_endpoint GET "/api/signals/monthly" "Monthly signals"
echo ""

echo "PORTFOLIO ENDPOINTS"
echo "==================="
test_endpoint GET "/api/portfolio/metrics" "Portfolio metrics"
test_endpoint GET "/api/trades" "Trade history"
echo ""

echo "CONTACT ENDPOINTS"
echo "================="
test_endpoint GET "/api/contact/submissions" "Get submissions"
test_endpoint POST "/api/contact" "Submit contact form"
echo ""

echo "HEALTH ENDPOINTS"
echo "================"
test_endpoint GET "/api/health/database" "Database health"
echo ""

echo "================================================"
echo "RESULTS"
echo "================================================"
echo -e "Total: $TOTAL | ${GREEN}Passed: $PASSED${NC} | ${RED}Failed: $FAILED${NC}"
echo ""

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✅ ALL TESTS PASSED!${NC}"
    exit 0
else
    echo -e "${RED}❌ SOME TESTS FAILED${NC}"
    exit 1
fi
