#!/bin/bash
# Quick Test Suite - Validates core functionality

set -e

echo "🧪 Quick Test Suite"
echo "=" "=".repeat(60)

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

FAILED=0

test_endpoint() {
  local name="$1"
  local url="$2"
  local expected="$3"

  echo -n "Testing $name... "

  response=$(curl -s "$url" || echo "ERROR")

  if echo "$response" | grep -q "$expected"; then
    echo -e "${GREEN}✅ PASS${NC}"
  else
    echo -e "${RED}❌ FAIL${NC}"
    echo "  Expected: $expected"
    echo "  Got: $(echo $response | head -c 200)"
    FAILED=$((FAILED + 1))
  fi
}

# Test API endpoints
test_endpoint "Health" "http://localhost:5001/api/health" '"success":true'
test_endpoint "Stocks" "http://localhost:5001/api/stocks?limit=1" '"success":true'
test_endpoint "Metrics" "http://localhost:5001/api/metrics/AACB" '"success":true'
test_endpoint "Signals" "http://localhost:5001/api/signals?symbol=AACB&limit=1" '"success":true'

# Database tests
echo ""
echo "📊 Database Tests"
export PGPASSWORD=stocks

test_table_count() {
  local table="$1"
  local min_count="$2"

  echo -n "Checking $table... "

  count=$(psql -h localhost -U stocks -d stocks -t -c "SELECT COUNT(*) FROM $table;" 2>/dev/null || echo "0")
  count=$(echo $count | tr -d ' ')

  if [ "$count" -ge "$min_count" ]; then
    echo -e "${GREEN}✅ $count records${NC}"
  else
    echo -e "${RED}❌ Only $count records (expected >= $min_count)${NC}"
    FAILED=$((FAILED + 1))
  fi
}

test_table_count "stock_symbols" 1000
test_table_count "company_profile" 100
test_table_count "price_daily" 10000
test_table_count "growth_metrics" 100

# Summary
echo ""
echo "=" "=".repeat(60)
if [ $FAILED -eq 0 ]; then
  echo -e "${GREEN}✅ All tests passed!${NC}"
  exit 0
else
  echo -e "${RED}❌ $FAILED tests failed${NC}"
  exit 1
fi
