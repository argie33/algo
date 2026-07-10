#!/bin/bash
# Test that all dashboard API endpoints return data

echo "Testing Dashboard API Endpoints"
echo "================================"
echo ""

API_BASE="http://localhost:3001"
AUTH_HEADER="Authorization: Bearer dev-admin"

# Test each endpoint the dashboard would call
endpoints=(
  "/api/portfolio"
  "/api/algo/status"
  "/api/algo/positions"
  "/api/algo/trades"
  "/api/algo/markets"
  "/api/market/sentiment"
)

for endpoint in "${endpoints[@]}"; do
  echo "Testing: $endpoint"
  status=$(curl -s -o /dev/null -w "%{http_code}" "$API_BASE$endpoint" -H "$AUTH_HEADER")
  if [ "$status" == "200" ]; then
    echo "  ✓ Status: $status - Data available"
  else
    echo "  ✗ Status: $status - ERROR"
  fi
  echo ""
done

echo "Dashboard Data Availability Summary:"
echo "===================================="
echo "All critical endpoints should return 200 status"
echo "This verifies the dashboard has data to display"
