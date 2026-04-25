#!/bin/bash

# Test script to verify the loader fix is working
# Run this AFTER running: python3 run-loaders.py

HOST="http://localhost:3001"

echo "╔════════════════════════════════════════════════════════════╗"
echo "║  LOADER FIX VERIFICATION TEST                             ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

check_table() {
  local table=$1
  local expected_min=$2
  local label=$3

  # Get count from database via API
  response=$(curl -s "$HOST/api/health" 2>/dev/null)
  count=$(echo "$response" | grep -o "\"$table\":[0-9]*" | cut -d: -f2 | head -1)

  if [ -z "$count" ] || [ "$count" = "-1" ]; then
    echo -e "${RED}✗${NC} $label: Not populated"
    return 1
  elif [ "$count" -lt "$expected_min" ]; then
    echo -e "${YELLOW}⚠${NC} $label: $count records (expected ≥ $expected_min)"
    return 1
  else
    echo -e "${GREEN}✓${NC} $label: $count records"
    return 0
  fi
}

echo "Checking database connectivity..."
if ! curl -s "$HOST/api/health" > /dev/null; then
  echo -e "${RED}✗ API server not responding at $HOST${NC}"
  echo "  Start the API server: node webapp/lambda/index.js"
  exit 1
fi
echo -e "${GREEN}✓${NC} API server is responding"
echo ""

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "DATA POPULATION CHECK (After Loaders Complete)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

PASS=0
FAIL=0

# Critical data sources
if check_table "stock_symbols" 4000 "Stock Symbols"; then
  ((PASS++))
else
  ((FAIL++))
fi

if check_table "price_daily" 200000 "Daily Price Data"; then
  ((PASS++))
else
  ((FAIL++))
fi

if check_table "technical_data_daily" 20000 "Technical Indicators"; then
  ((PASS++))
else
  ((FAIL++))
fi

if check_table "stock_scores" 4000 "Stock Scores"; then
  ((PASS++))
else
  ((FAIL++))
fi

echo ""
echo "Earnings & Analyst Data (Should be populated after loaders)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# These should be populated NOW (were broken before)
if check_table "earnings_estimates" 4000 "Earnings Estimates"; then
  ((PASS++))
else
  ((FAIL++))
fi

if check_table "analyst_upgrade_downgrade" 3000 "Analyst Upgrades"; then
  ((PASS++))
else
  ((FAIL++))
fi

if check_table "analyst_sentiment_analysis" 3000 "Analyst Sentiment"; then
  ((PASS++))
else
  ((FAIL++))
fi

if check_table "buy_sell_daily" 3000 "Trading Signals"; then
  ((PASS++))
else
  ((FAIL++))
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "SUMMARY"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo -e "${GREEN}Passed: $PASS${NC}"
echo -e "${RED}Failed: $FAIL${NC}"

if [ $FAIL -eq 0 ]; then
  echo ""
  echo -e "${GREEN}✓ All data populated successfully!${NC}"
  echo ""
  echo "Frontend should now show:"
  echo "  • Earnings forecasts"
  echo "  • Analyst ratings"
  echo "  • Trading signals"
  echo "  • All technical indicators"
  exit 0
else
  echo ""
  echo -e "${YELLOW}⚠ Some data is missing${NC}"
  echo ""
  echo "Possible reasons:"
  echo "  1. Loaders are still running (takes 3-5 hours)"
  echo "  2. Some loaders failed silently (check .loader-progress.json)"
  echo "  3. API connection issue"
  echo ""
  echo "Check progress:"
  echo "  cat .loader-progress.json"
  exit 1
fi
