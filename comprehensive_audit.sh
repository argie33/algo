#!/bin/bash

HOST="http://localhost:3001"

echo "╔════════════════════════════════════════════════════════╗"
echo "║        COMPREHENSIVE SYSTEM AUDIT                     ║"
echo "╚════════════════════════════════════════════════════════╝"
echo ""

test_endpoint() {
  local path=$1
  local label=$2
  result=$(curl -s -w "\n%{http_code}" "$HOST$path" 2>/dev/null | tail -1)
  
  if [[ "$result" == "200" ]]; then
    echo "  OK  | $label"
    return 0
  elif [[ "$result" == "301" ]]; then
    echo "  REDIR | $label"
    return 0
  else
    echo "  FAIL ($result) | $label"
    return 1
  fi
}

echo "CORE ENDPOINTS:"
test_endpoint "/api/health" "Health check"
test_endpoint "/api/diagnostics" "Diagnostics"
test_endpoint "/api/stocks" "Stock list"

echo ""
echo "SCORE ENDPOINTS:"
test_endpoint "/api/scores" "Scores root"
test_endpoint "/api/scores/all" "All scores"
test_endpoint "/api/scores/stockscores" "Stock scores"

echo ""
echo "SIGNAL ENDPOINTS:"
test_endpoint "/api/signals" "Signals root"
test_endpoint "/api/signals/daily" "Daily signals"
test_endpoint "/api/signals/stocks" "Stock signals"

echo ""
echo "SENTIMENT ENDPOINTS:"
test_endpoint "/api/sentiment" "Sentiment root"
test_endpoint "/api/sentiment/summary" "Sentiment summary"
test_endpoint "/api/sentiment/analyst" "Analyst sentiment"

echo ""
echo "PRICE/TECHNICAL ENDPOINTS:"
test_endpoint "/api/price/history/AAPL" "Price history"
test_endpoint "/api/technicals/AAPL" "Technicals"

echo ""
echo "DATA ENDPOINTS:"
test_endpoint "/api/earnings/info?symbol=AAPL" "Earnings"
test_endpoint "/api/financials/AAPL/balance-sheet" "Financials"
test_endpoint "/api/sectors" "Sectors"

echo ""
echo "ANALYST ENDPOINTS:"
test_endpoint "/api/analysts" "Analysts root"
test_endpoint "/api/analysts/list" "Analysts list"
test_endpoint "/api/analysts/upgrades" "Analyst upgrades"

echo ""
echo "MARKET ENDPOINTS:"
test_endpoint "/api/market/overview" "Market overview"

echo ""
echo ""
echo "DATA QUALITY CHECKS:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Check S&P 500 count
SP500=$(curl -s "$HOST/api/scores/stockscores?limit=1" | grep -o '"total":[0-9]*' | cut -d: -f2)
echo "S&P 500 stocks with scores: $SP500 (target: ~500)"

# Check all stocks count  
curl -s "$HOST/api/stocks?limit=1" > /tmp/stocks.json
ALLSTOCKS=$(grep -o '"total":[0-9]*' /tmp/stocks.json | head -1 | cut -d: -f2)
echo "Total stocks in system: $ALLSTOCKS (target: 4969)"

echo ""
echo "═══════════════════════════════════════════════════════════════"

