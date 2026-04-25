#!/bin/bash

# Endpoints that are ACTUALLY called by the frontend pages
endpoints=(
  "/api/health"
  "/api/health/database"
  "/api/economic/calendar"
  "/api/earnings/calendar"
  "/api/market/overview"
  "/api/sectors"
  "/api/market/indicators"
  "/api/market/indices"
  "/api/market/volatility"
  "/api/sentiment/current"
  "/api/user/profile"
  "/api/portfolio/metrics"
  "/api/user/settings"
  "/api/trades"
  "/api/trades/summary"
)

failed=()
passed=0
for endpoint in "${endpoints[@]}"; do
  status=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:3001$endpoint")
  if [ "$status" == "200" ]; then
    echo "✅ $endpoint"
    ((passed++))
  else
    echo "❌ $endpoint - HTTP $status"
    failed+=("$endpoint")
  fi
done

echo ""
echo "Passed: $passed / ${#endpoints[@]}"
if [ ${#failed[@]} -gt 0 ]; then
  echo "Failed: ${#failed[@]}"
fi
