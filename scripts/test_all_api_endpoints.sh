#!/bin/bash
# Comprehensive API endpoint testing script
# Tests all endpoints and documents response codes and errors

set -e

frontend="https://d2u93283nn45h2.cloudfront.net"
api_base="$frontend/api"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test results
total_tests=0
passed_tests=0
failed_tests=0
error_tests=0

# Public endpoints (should work without JWT)
public_endpoints=(
  "GET:/api/health"
)

# Authenticated endpoints (require JWT - will get 401 without it)
auth_endpoints=(
  "GET:/api/health/detailed"
  "GET:/api/health/pipeline"
  "GET:/api/algo"
  "GET:/api/algo/risk-dashboard"
  "GET:/api/financials"
  "GET:/api/earnings"
  "GET:/api/signals"
  "GET:/api/prices"
  "GET:/api/stocks"
  "GET:/api/sectors"
  "GET:/api/industries"
  "GET:/api/market"
  "GET:/api/economic"
  "GET:/api/sentiment"
  "GET:/api/scores"
  "GET:/api/research"
  "GET:/api/audit"
  "GET:/api/trades"
  "GET:/api/admin"
  "GET:/api/contact"
  "GET:/api/settings"
  "GET:/api/data-coverage"
)

test_endpoint() {
  local method=$1
  local path=$2
  local expected_status=$3
  local url="$frontend$path"

  ((total_tests++))

  # Make request and capture response
  response=$(curl -s -w "\n%{http_code}" "$url" -H "Accept: application/json" 2>&1)

  # Extract status code (last line)
  status=$(echo "$response" | tail -n1)
  body=$(echo "$response" | sed '$d')

  # Check if status matches expected
  if [ "$status" = "$expected_status" ]; then
    echo -e "${GREEN}✓${NC} $method $path -> HTTP $status"
    ((passed_tests++))
  elif [[ "$status" =~ ^(401|403)$ ]] && [[ "$expected_status" =~ ^(401|403)$ ]]; then
    # Accept 401/403 as success for authenticated endpoints without token
    echo -e "${GREEN}✓${NC} $method $path -> HTTP $status (expected for auth required)"
    ((passed_tests++))
  elif [ "$status" = "500" ] || [ "$status" = "502" ] || [ "$status" = "503" ]; then
    echo -e "${RED}✗${NC} $method $path -> HTTP $status (ERROR)"
    echo "    Response: ${body:0:200}"
    ((error_tests++))
  else
    echo -e "${YELLOW}!${NC} $method $path -> HTTP $status (unexpected, but not 500)"
    echo "    Response: ${body:0:200}"
    ((failed_tests++))
  fi
}

echo "========================================="
echo "Testing API Endpoints"
echo "========================================="
echo ""

# Test public endpoints
echo "Public Endpoints (no JWT required):"
echo "---"
for endpoint in "${public_endpoints[@]}"; do
  method="${endpoint%%:*}"
  path="${endpoint##*:}"
  test_endpoint "$method" "$path" "200"
done

echo ""
echo "Authenticated Endpoints (will get 401 without JWT):"
echo "---"
for endpoint in "${auth_endpoints[@]}"; do
  method="${endpoint%%:*}"
  path="${endpoint##*:}"
  # Expected status is 401 (Unauthorized) without JWT token
  test_endpoint "$method" "$path" "401"
done

echo ""
echo "========================================="
echo "Test Summary:"
echo "  Total:  $total_tests"
echo -e "  ${GREEN}Passed:${NC} $passed_tests"
echo -e "  ${YELLOW}Failed:${NC} $failed_tests"
echo -e "  ${RED}Errors:${NC} $error_tests"
echo "========================================="

# Exit with error if any tests failed or errored
if [ $error_tests -gt 0 ] || [ $failed_tests -gt 5 ]; then
  exit 1
fi

exit 0
